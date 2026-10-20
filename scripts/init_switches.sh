#!/bin/bash

# Init switches queue depth (s1, s2, s3)
# set_queue_depth <nb_pkts> [<egress_port> [<priority>]]
simple_switch_CLI --thrift-port 9090 <<< 'set_queue_depth 200'
# simple_switch_CLI --thrift-port 9091 <<< 'set_queue_depth 200'
# simple_switch_CLI --thrift-port 9092 <<< 'set_queue_depth 200'

# Queue rate on s1 (total capacity split on egress ports)
# set_queue_rate <rate_pps> [<egress_port> [<priority>]]
CAPA_PPS=350
EGRESS_PORTS=(2 3)

# Parse optional total capacity arg that will erase the default
while [ $# -gt 0 ]; do
    case "$1" in
        --capa|--capa-pps|--infra-pps)
            if [ -n "${2:-}" ]; then
                CAPA_PPS="$2"
                shift 2
            else
                shift
            fi
            ;;
        *)
            shift
            ;;
    esac
done

# Split total capacity across egress ports 
per_port=$((CAPA_PPS / ${#EGRESS_PORTS[@]}))
rem=$((CAPA_PPS % ${#EGRESS_PORTS[@]}))

# Apply queue rates for each port
for idx in "${!EGRESS_PORTS[@]}"; do
    port=${EGRESS_PORTS[$idx]}
    rate=$per_port
    if [ $idx -lt $rem ]; then
        rate=$((rate + 1))
    fi
    simple_switch_CLI --thrift-port 9090 <<< "set_queue_rate $rate $port"
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Init ECMP tables (50-50 on MyIngress.ecmp_to_nhop)
"$SCRIPT_DIR/init_tables.py" --p4info "$PROJECT_DIR/build/switch.p4.p4info.txt"
