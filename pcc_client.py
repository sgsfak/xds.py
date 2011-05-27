#!/usr/bin/python
"""A PCC-10 server example"""

from gevent import monkey; monkey.patch_all()
from gevent import wsgi
from optparse import OptionParser
from lxml import etree
import urllib2
import socket
import sys
import time
import uuid

PATH = '/pcc10/'
MYIP = socket.gethostbyname_ex(socket.gethostname())[2][0]
PORT = 8088
MYENDPOINT = 'http://%s:%s%s' % (MYIP, PORT, PATH)

NS = {"soap":"http://www.w3.org/2003/05/soap-envelope", 
      "wsa":"http://www.w3.org/2005/08/addressing",
      'wsnt': 'http://docs.oasis-open.org/wsn/b-2'
      }
PCC9_ACTION = 'urn:hl7-org:v3:QUPC_IN043100UV01'
PCC10_ACK_ACTION = 'urn:hl7-org:v3:MCCI_IN000002UV01'
SERVER = 'http://localhost:9080/pcc/'
CARE_PROVISION_CODE = 'MEDLIST'
PATIENT_ID = '*'

def build_soap_msg(body, replyAddr = None, action = PCC9_ACTION, relTo = None):
    SOAP = "{%s}" % NS['soap']
    WSA = "{%s}" % NS['wsa']
    env = etree.Element(SOAP+"Envelope", nsmap=NS)
    hdr = etree.SubElement(env, SOAP+"Header")
    msg = etree.SubElement(hdr, WSA+"MessageID")
    msg.text = uuid.uuid4().urn
    act = etree.SubElement(hdr, WSA+"Action")
    act.set(SOAP+"mustUnderstand", "true")
    act.text = action
    if replyAddr is not None:
        rt = etree.SubElement(hdr, WSA+"ReplyTo")
        radd = etree.SubElement(rt, WSA+"Address")
        radd.text = replyAddr
    if relTo is not None:
        rt = etree.SubElement(hdr, WSA+"RelatesTo")
        rt.text = relTo
    bd = etree.SubElement(env, SOAP+"Body")
    bd.append(body)
    return env

def build_pcc10_ack():
    ts = time.strftime('%Y%m%d%H%M%S',time.gmtime())
    ackId = uuid.uuid4().hex
    typecode = 'AA'
    pcc10_ack = """
    <MCCI_IN000002UV01 ITSVersion='XML_1.0' xmlns='urn:hl7-org:v3'>
	<id root='' extension='%s'/>
	<creationTime value='%s'/>
        <interactionId extension='MCCI_IN000002UV01' root='2.16.840.1.113883.5'/>
        <processingModeCode code='T'/> <!-- T means current processing -->
	<acceptAckCode code='NE'/>
	<receiver typeCode='RCV'>
		<device classCode='DEV' determinerCode='INSTANCE'>
			<id/>
		</device>
	</receiver>
	<sender typeCode='RCV'>
		<device classCode='DEV' determinerCode='INSTANCE'>
			<id/>
		</device>
	</sender>
        <acknowledgement typeCode='%s'/>
    </MCCI_IN000002UV01>""" % (ackId, ts, typecode)
    
    return build_soap_msg(etree.fromstring(pcc10_ack),
                          action = PCC10_ACK_ACTION)

def send_pcc9(server_url, callback_url, pcc9):
    soap = build_soap_msg( etree.fromstring(pcc9), replyAddr = callback_url)
    req = urllib2.Request(server_url)
    req.add_header('content-type',
                   'application/soap+xml;charset=utf-8;action="%s"' % (PCC9_ACTION,))
    req.add_data(etree.tostring(soap, encoding='utf-8'))
    try:
        fp = urllib2.urlopen(req)
        response = fp.read()
        # print 'SUBMITTED PCC-9 AND GOT\n',response
        x = etree.fromstring(response)        
        l = x.xpath("/soap:Envelope/soap:Header/wsnt:SubscriptionReference/wsa:Address",
                    namespaces=NS)
        if not l:
            return None
        return l[0].text
    except urllib2.HTTPError, ex:
        msg = ex.read()
        print "PCC9 Error: %s %s" % (ex.code, msg)
        raise ex
    except urllib2.URLError, ex:
        print "PCC9 Error: %s " % (ex.reason)
    except:
        print "PCC9 Unexpected error:", sys.exc_info()[0]
        raise
    
def pcc10_handler(env, start_response):
    if env['REQUEST_METHOD'].upper()  == 'GET':
        start_response('200 OK', [('Content-Type', 'text/html')])
        return ["Hi! I am waiting for PCC-10 messages to be POSTed at <a href='%s'>%s</a>" %
                (MYENDPOINT, MYENDPOINT)]
    elif env['PATH_INFO'] == PATH:
        msg = env['wsgi.input'].read()
        print 'I got new PCC-10!!'
        #print 'Here it is:',msg
        start_response('200 OK',
                       [('Content-Type',
                         'application/soap+xml;charset=utf-8;action="%s"' % PCC10_ACK_ACTION)])
        soap = build_pcc10_ack()
        return [etree.tostring(soap, encoding='utf-8')]
    else:
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return ['<h1>Not Found</h1>']

def delete_subscription(sub_url):
    req = urllib2.Request(sub_url, data='',
                          headers={'X-HTTP-Method-Override': 'DELETE',
                                   'Content-type': 'application/json'})
    try:
        fp = urllib2.urlopen(req)
        meta = fp.info()
        print 'Subscription DELETED!'
    except urllib2.HTTPError, ex:
        msg = ex.read()
        print "Error: %s %s" % (ex.code, msg)
        raise ex
    except urllib2.URLError, ex:
        print "Error: %s " % (ex.reason)
    except:
        print "Unexpected error:", sys.exc_info()[0]
        raise
    
PCODES = ['HISTMEDLIST',
          'DISCHMEDLIST',
          'IMMUCAT',
          'MEDCCAT',
          'CURMEDLIST',
          'RXCAT',
          'RISKLIST',
          'PROBLIST',
          'PSVCCAT',
          'COBSCAT',
          'CONDLIST',
          'MEDLIST',
          'LABCAT',
          'INTOLIST',
          'DICAT',
          '*']

def parse_options():
    parser = OptionParser(usage = "usage: %prog [options]")
    parser.set_defaults(patient_id=PATIENT_ID, provision_code=CARE_PROVISION_CODE, server=SERVER, nbr=1)
    parser.add_option("-p", action="store", dest="patient_id", help='the patient id. Default: %s'%(PATIENT_ID,))
    parser.add_option("-c", action="store", choices=PCODES, dest="provision_code",
                      help='the care provision code (See http://goo.gl/lSMg) Default:%s'%(CARE_PROVISION_CODE,))
    parser.add_option("-s", "--data-source", action="store", dest="server",
                      help='the Data Source endpoint (where the PCC-9 will be send to) Default: %s'%(SERVER,))
    parser.add_option("-n", action="store", dest="nbr", type="int",
                      help='Submit that many subscriptions. Used for benchmarking... Default: 1')
    (options, args) = parser.parse_args()
    return options

if __name__ == "__main__":
    options = parse_options()
    patient_id = options.patient_id
    provision_code = options.provision_code
    server = options.server
    n = options.nbr
    with open("pcc-9.template.xml") as f:
        pcc9 = f.read()
    pcc9 = pcc9.replace('$PATIENT_ID$', patient_id.replace('&', '&amp;')).replace('$CARE_PROVISION_CODE$', provision_code)
    refs = []
    for i in xrange(n):
        ref = send_pcc9(server, MYENDPOINT, pcc9)
        print 'I have sent PCC-9 for patient: %s and care prov code: %s' % (patient_id,
                                                                            provision_code)
        print 'SubscriptionRef:%s' % ref
        if ref is not None:
            refs.append(ref)
    if len(refs) == 0:
        print "No subscriptions registered!!"
        sys.exit()
    print 'Registered %s subscription(s) out of %s\nWaiting for PCC-10 on %s...' % (len(refs), options.nbr, PORT)
    s = wsgi.WSGIServer(('', PORT), pcc10_handler)
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        s.stop()
        print 'exiting...deleting subscription...'
        for ref in refs:
            delete_subscription(ref)

