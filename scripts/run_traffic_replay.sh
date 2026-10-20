#!/bin/bash

# Make sure Python module 'yaml' is installed (pip install PyYAML)
# as well as tcpreplay (sudo apt install tcpreplay)

# TODO. Update CAPTURES_DIR according to where the pcap files are stored.
CAPTURES_DIR="$HOME/captures"
# CAPTURES_DIR="$HOME/tmp/captures"

# Default pcap to replay
DEFAULT_PCAP="$CAPTURES_DIR/univ1_pt1_filtered_pnat_subset.pcap"

# Default value for the Python virtual environment (i.e. use p4setup.bash)
VIRTUAL_ENV=1

# Optional: skip MRI telemetry packets (useful for very raw dataplane-only runs)
NO_MRI=0

# Traffic params
IN_PPS=340
CAPA_PPS=""

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TELEMETRY_DIR="$(cd -- "$PROJECT_DIR/telemetry" && pwd)"

echo "Using PROJECT_DIR = $PROJECT_DIR"
echo "Using SCRIPT_DIR = $SCRIPT_DIR"
echo "Using TELEMETRY_DIR = $TELEMETRY_DIR"

usage() {
    echo "Usage: $0 [--no-venv] [--no-mri] [--in-pps N] [--capa N] [pcap ...]" >&2
}

# Parse args
PCAP_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --no-venv)
            VIRTUAL_ENV=0
            shift
            ;;
        --no-mri)
            NO_MRI=1
            shift
            ;;
        --ecmp)
            # Kept for backward compatibility: ECMP is handled at controller level.
            # In run_traffic_replay.sh, keep MRI enabled by default.
            shift
            ;;
        # Parse optional rate/capacity args
        --in-pps|--pps)
            if [ -z "${2:-}" ]; then
                echo "Missing value for $1" >&2
                usage
                exit 2
            fi
            IN_PPS="$2"
            shift 2
            ;;
        --capa|--capa-pps|--infra-pps)
            if [ -z "${2:-}" ]; then
                echo "Missing value for $1" >&2
                usage
                exit 2
            fi
            CAPA_PPS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            PCAP_ARGS+=("$1")
            shift
            ;;
    esac
done

# Set mn_host based on VIRTUAL_ENV
if [ $VIRTUAL_ENV -eq 1 ]; then
    # in the local ./m script, we add quotes in case of args
    mn_host="$SCRIPT_DIR/m"
    P4SETUP="$HOME/p4setup.bash"
else
    mn_host="$HOME/mininet/util/m"
fi

# In ECMP baseline mode (no controller), we still want a logs_* folder
# so batch scripts can archive pcaps and post-process throughput.
if [ $NO_MRI -eq 1 ]; then
    TEST_NAME=$(python3 -c "import importlib.util, os; p=os.path.join('..','controlplane','controller_config.py'); s=importlib.util.spec_from_file_location('cfg', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(getattr(m,'CONTROLLER_CONFIG',{}).get('test_name',''))" 2>/dev/null)
    if [ -z "$TEST_NAME" ]; then
        TEST_NAME=$(date +%Y%m%d_%H%M%S)
    fi
    LOG_DIR="$PROJECT_DIR/logs_${TEST_NAME}"
    echo "[ECMP] Creating logs dir: $LOG_DIR"
    mkdir -p "$LOG_DIR"
fi

echo "Traffic input rate: ${IN_PPS} pps"
if [ -n "$CAPA_PPS" ]; then
    echo "Infra capacity: ${CAPA_PPS} pps"
fi

######################
# Array to store PIDs of child processes
pids=()
# Function to kill them all :)
cleanup() {
    echo "SIGINT received or end of scenario. Terminating child processes..."
    for pid in "${pids[@]}"; do
        echo "Killing process $pid (SIGTERM)"
        sudo kill -TERM "$pid" 2>/dev/null
    done
}
# Set up trap to cleanup function on SIGINT (CTRL+C)
trap cleanup SIGINT
######################

######################
# Init switches (queue depth, queue rate, ECMP tables)
######################
echo "Init switches..."

# Propagate infra capacity to switch init if provided
INIT_ARGS=()
if [ -n "$CAPA_PPS" ]; then
    INIT_ARGS+=("--capa" "$CAPA_PPS")
fi
sudo -E env PATH="$PATH" "$SCRIPT_DIR/init_switches.sh" "${INIT_ARGS[@]}"

sleep 5

######################
# Telemetry
######################
if [ $NO_MRI -eq 1 ]; then
    echo "*** ECMP mode: skipping MRI telemetry packets"
else
    CONFIG_FILE="$TELEMETRY_DIR/telemetry_config.yaml"
    HOSTS=$(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('$CONFIG_FILE'))['hosts'].keys()))")

    echo "*** Starting telemetry packet transmission on hosts [$HOSTS]"
    for host in $HOSTS; do
        echo "On $host..."
        if [ $VIRTUAL_ENV -eq 1 ] ; then
            $mn_host $host "bash -c 'source $P4SETUP && $TELEMETRY_DIR/send_mri.py $host'" > /dev/null &
        else
            $mn_host $host $TELEMETRY_DIR/send_mri.py $host > /dev/null &
        fi
        pids+=($!)
    done
fi

######################
# Data traffic
######################
echo "*** Replaying traffic on host h1 with tcpreplay..."

if [ $VIRTUAL_ENV -eq 1 ] ; then
    # run sniffer on receiver to count received packets
    echo "Starting Python receiver on h6 to count packets..."
    $mn_host h6 "bash -c 'source $P4SETUP && python3 $SCRIPT_DIR/receive_data.py'" &
    pids+=($!)

    if [ ${#PCAP_ARGS[@]} -eq 0 ]; then
        # Replay existing traffic
        $mn_host h1 "bash -c 'source $P4SETUP && tcpreplay -i eth0 -l 1 -p $IN_PPS $DEFAULT_PCAP'"
    else
        # Replay specified pcaps from command line
        echo "*** Replaying the following pcaps: ${PCAP_ARGS[*]}"
        for pcap in "${PCAP_ARGS[@]}"; do
            # if the argument does not contain '/', we take it from $CAPTURES_DIR
            if [[ "$pcap" != */* ]]; then
                pcap="$CAPTURES_DIR/$pcap"
            fi
            echo "  -> $pcap"
            $mn_host h1 "bash -c 'source $P4SETUP && tcpreplay -i eth0 -l 1 -p $IN_PPS $pcap'"
        done
    fi
else
    # run sniffer on receiver to count received packets
    echo "Starting Python receiver on h6 to count packets..."
    $mn_host h6 python3 $SCRIPT_DIR/receive_data.py &
    pids+=($!)

    if [ ${#PCAP_ARGS[@]} -eq 0 ]; then
        # Replay existing traffic
        $mn_host h1 tcpreplay -i eth0 -l 1 -p $IN_PPS $DEFAULT_PCAP
    else
        echo "*** Replaying the following pcaps: ${PCAP_ARGS[*]}"
        for pcap in "${PCAP_ARGS[@]}"; do
            if [[ "$pcap" != */* ]]; then
                pcap="$CAPTURES_DIR/$pcap"
            fi
            echo "  -> $pcap"
            $mn_host h1 tcpreplay -i eth0 -l 1 -p $IN_PPS "$pcap"
        done
    fi
fi

echo "END OF SCENARIO"
sleep 5

# In ECMP baseline mode, archive pcaps in the logs folder so they are not
# overwritten by the next run (batch), even without a controller.
if [ $NO_MRI -eq 1 ]; then
    PCAP_SRC_DIR=$(grep -E '^[[:space:]]*PCAP_DIR[[:space:]]*[:]?=' ../Makefile 2>/dev/null | head -n1 | sed -E 's/^[^=]*=//' | xargs)
    PCAP_SRC_DIR=$(eval echo "${PCAP_SRC_DIR:-../pcaps}")
    if [ ! -d "$PCAP_SRC_DIR" ]; then
        PCAP_SRC_DIR="../pcaps"
    fi
    echo "[ECMP] Archiving pcaps from $PCAP_SRC_DIR to $LOG_DIR"
    for f in s1-eth1_in.pcap s6-eth3_out.pcap; do
        if [ -f "$PCAP_SRC_DIR/$f" ]; then
            cp -f "$PCAP_SRC_DIR/$f" "$LOG_DIR/" 2>/dev/null || sudo cp -f "$PCAP_SRC_DIR/$f" "$LOG_DIR/" || true
        else
            echo "[ECMP] WARNING: missing pcap: $PCAP_SRC_DIR/$f"
        fi
    done
fi

echo "Terminating child processes (telemetry sender(s) and Python receiver on h6)"
echo ${pids[@]}
cleanup
echo "All child processes terminate correctly."
