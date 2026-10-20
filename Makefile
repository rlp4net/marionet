BMV2_SWITCH_EXE = simple_switch_grpc
TOPO = dataplane/topo/topology.json
LOG_LEVEL = info
DEFAULT_PROG = dataplane/switch.p4

P4_MININET ?= $(HOME)/p4-mininet
export P4_MININET
include $(P4_MININET)/Makefile
