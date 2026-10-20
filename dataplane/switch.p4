/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

const bit<8>  TCP_PROTOCOL  = 0x06;
const bit<8>  UDP_PROTOCOL = 0x11;
const bit<16> TYPE_IPV4 = 0x800;
const bit<16> TYPE_DOT1Q = 0x8100;
const bit<5>  IPV4_OPTION_MRI = 31;
const bit<32> REPORT_MIRROR_SESSION_ID = 500;
const bit<16> TYPE_SRCROUTING = 0x1234;

#define MAX_HOPS 9

#define INT_SOURCE  0
#define INT_TRANSIT 1
#define INT_SINK    2

// #define PKT_INSTANCE_TYPE_NORMAL 0
// #define PKT_INSTANCE_TYPE_INGRESS_CLONE 1
// #define PKT_INSTANCE_TYPE_EGRESS_CLONE 2
// #define PKT_INSTANCE_TYPE_COALESCED 3
// #define PKT_INSTANCE_TYPE_INGRESS_RECIRC 4
// #define PKT_INSTANCE_TYPE_REPLICATION 5
// #define PKT_INSTANCE_TYPE_RESUBMIT 6

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

typedef bit<32> switchID_t;
typedef bit<32> qdepth_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header dot1q_t {
    bit<3>  priority;  // Priority code point (PCP)
    bit<1>  dei;       // Drop eligible indicator (DEI)
    bit<12> vid;       // VLAN identifier (VID)
    bit<16> etherType; // From Ethernet Header
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

header ipv4_option_t {
    bit<1> copyFlag;
    bit<2> optClass;
    bit<5> option;
    bit<8> optionLength;
}

header mri_t {
    bit<16>  count;
}

header switch_t {
    switchID_t  swid;
    qdepth_t    qdepth;
}

header srcRoute_t {
    bit<1>    bos;
    bit<15>   port;
}

header tcp_t{
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<4>  res;
    bit<1>  cwr;
    bit<1>  ece;
    bit<1>  urg;
    bit<1>  ack;
    bit<1>  psh;
    bit<1>  rst;
    bit<1>  syn;
    bit<1>  fin;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

header udp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<16> length_;
    bit<16> checksum;
}

struct ingress_metadata_t {
    bit<16>  count;
}

struct parser_metadata_t {
    bit<16>  remaining;
}

struct headers {
    ethernet_t           ethernet;
    srcRoute_t[MAX_HOPS] srcRoutes;
    dot1q_t              dot1q;
    ipv4_t               ipv4;
    ipv4_option_t        ipv4_option;
    mri_t                mri;
    switch_t[MAX_HOPS]   swtraces;
    udp_t                udp;
    tcp_t                tcp;
}

struct metadata {
    ingress_metadata_t   ingress_metadata;
    parser_metadata_t   parser_metadata;
    bit<16> ecmp_hash;
    bit<16> srcPort;
    bit<16> dstPort;
    bit<8> int_role; // SOURCE, TRANSIT, SINK
}

error { IPHeaderTooShort }

/*************************************************************************
************************* P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t smeta) {

    state start {
        transition parse_ethernet;
    }

    state parse_srcRouting {
        //log_msg("srcrouting packet received");

        packet.extract(hdr.srcRoutes.next);
        transition select(hdr.srcRoutes.last.bos) {
            1: parse_ipv4;
            default: parse_srcRouting;
        }
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_DOT1Q: parse_dot1q;
            TYPE_IPV4: parse_ipv4;
            TYPE_SRCROUTING: parse_srcRouting;
            default: accept;
        }
    }

    state parse_dot1q {
        packet.extract(hdr.dot1q);
        transition select(hdr.dot1q.etherType) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        verify(hdr.ipv4.ihl >= 5, error.IPHeaderTooShort);
        transition select(hdr.ipv4.ihl) {
            5             : parse_transport;
            default       : parse_ipv4_option;
        }
    }

    state parse_transport {
        transition select (hdr.ipv4.protocol) {
            UDP_PROTOCOL: parse_udp; 
            TCP_PROTOCOL: parse_tcp;
            default: accept;
        }
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        meta.srcPort = hdr.tcp.srcPort;
        meta.dstPort = hdr.tcp.dstPort;
        //log_msg("TCP packet received");
        transition accept;
    }

    state parse_udp {
        packet.extract(hdr.udp);
        meta.srcPort = hdr.udp.srcPort;
        meta.dstPort = hdr.udp.dstPort;
        //log_msg("UDP packet received");
        transition accept;
    }

    state parse_ipv4_option {
        packet.extract(hdr.ipv4_option);
        transition select(hdr.ipv4_option.option) {
            IPV4_OPTION_MRI: parse_mri;
            default: parse_transport;
        }
    }

    state parse_mri {
        packet.extract(hdr.mri);
        meta.parser_metadata.remaining = hdr.mri.count;
        transition select(meta.parser_metadata.remaining) {
            0 : parse_transport;
            default: parse_swtrace;
        }
    }

    state parse_swtrace {
        packet.extract(hdr.swtraces.next);
        meta.parser_metadata.remaining = meta.parser_metadata.remaining  - 1;
        transition select(meta.parser_metadata.remaining) {
            0 : parse_transport;
            default: parse_swtrace;
        }
    }

}

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   **************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}


/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   ********************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t smeta) {

    action drop() {
        mark_to_drop(smeta);
    }

    action set_ecmp(bit<8> num_nhops) {
        hash(
            meta.ecmp_hash,
            HashAlgorithm.crc16,
            (bit<1>)0,
            { hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol, meta.srcPort, meta.dstPort },
            (bit<8>)num_nhops);
    }

    action set_nhop(macAddr_t dstAddr, egressSpec_t port) {
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
        smeta.egress_spec = port;

        log_msg("HASH = {} and PORT = {}",{meta.ecmp_hash, port});
    }

    action set_int_role(bit<8> role) {
        meta.int_role = role;
    }

    // Source routing
    action srcRoute_nhop() {
        smeta.egress_spec = (bit<9>)hdr.srcRoutes[0].port;
        hdr.srcRoutes.pop_front(1);
    }

    action srcRoute_finish() {
        hdr.ethernet.etherType = TYPE_IPV4;
    }

    // direct_counter(CounterType.packets_and_bytes) ipv4_lpm_counter; 

    // IPv4 forwarding table
    table ipv4_lpm {
        key = { hdr.ipv4.dstAddr: lpm; }
        actions = {
            set_nhop;
            set_ecmp;
            NoAction;
            drop;
        }
        // counters = ipv4_lpm_counter;
        size = 256;
        default_action = NoAction;        
    }

    // ECMP table, used when (equal cost) multiple paths exist
    table ecmp_to_nhop {
        key = {
            meta.ecmp_hash: exact;
        }
        actions = {
            set_nhop;
            NoAction;
        }
        size = 256;
        default_action = NoAction;  
    }

    // In-band network telemetry table, to set the switch's role (SOURCE, SINK...)
    table int_role {
        actions = {
            set_int_role;
            NoAction;
        }
        default_action = NoAction();
    }

    apply {
        if (hdr.srcRoutes[0].isValid()){
            if (hdr.srcRoutes[0].bos == 1){
                srcRoute_finish();
            }
            srcRoute_nhop();
            if (hdr.ipv4.isValid()){
                hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
            }
        } else if (hdr.ipv4.isValid()) {

            switch (ipv4_lpm.apply().action_run) {
                set_ecmp: {ecmp_to_nhop.apply();}
            }
            int_role.apply();
            if (hdr.mri.isValid() && meta.int_role == INT_SINK) {
                // clone packet to egress (to send to controller)
                clone(CloneType.I2E, REPORT_MIRROR_SESSION_ID);
            }
        }
    }

}

/*************************************************************************
*****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t smeta) {

    action add_swtrace(switchID_t swid) {
        hdr.mri.count = hdr.mri.count + 1;
        hdr.swtraces.push_front(1);

        hdr.swtraces[0].setValid();
        hdr.swtraces[0].swid = swid;
        hdr.swtraces[0].qdepth = (qdepth_t)smeta.deq_qdepth;

        hdr.ipv4.ihl = hdr.ipv4.ihl + 2;
        hdr.ipv4_option.optionLength = hdr.ipv4_option.optionLength + 8;
        hdr.ipv4.totalLen = hdr.ipv4.totalLen + 8;
    }

    table swtrace {
        actions = {
            add_swtrace;
            NoAction;
        }
        default_action = NoAction();
    }

    apply {
        if (hdr.mri.isValid()) {
            swtrace.apply();
        }
    }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   ***************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
***********************  D E P A R S E R  ********************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.dot1q);
        packet.emit(hdr.srcRoutes);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.ipv4_option);
        packet.emit(hdr.mri);
        packet.emit(hdr.swtraces);
        packet.emit(hdr.udp);
        packet.emit(hdr.tcp);
    }
}

/*************************************************************************
*************************  S W I T C H  **********************************
*************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
