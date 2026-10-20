BMV2_SWITCH_EXE = simple_switch_grpc
TOPO = dataplane/topo/topology.json
LOG_LEVEL = info
DEFAULT_PROG = dataplane/switch.p4

P4_MININET=~/p4-mininet
include $(P4_MININET)/Makefile
