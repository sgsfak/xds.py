#!/usr/bin/python
"""A PCC-10 server example"""

from gevent import wsgi
from optparse import OptionParser
from lxml import etree
import urllib2
import socket
import sys

PATH = '/pcc10/'
MYIP = socket.gethostbyname_ex(socket.gethostname())[2][0]
PORT = 8088
MYENDPOINT = 'http://%s:%s%s' % (MYIP, PORT, PATH)

NS = {"soap":"http://www.w3.org/2003/05/soap-envelope", 
      "wsa":"http://www.w3.org/2005/08/addressing"
      }
ACTION = 'urn:hl7-org:v3:QUPC_IN043100UV01'
SERVER = 'http://localhost:9080/pcc/'
CARE_PROVISION_CODE = 'MEDLIST'
PATIENT_ID = 'pat1234'

def build_soap_msg(body, replyAddr):
    SOAP = "{%s}" % NS['soap']
    WSA = "{%s}" % NS['wsa']
    env = etree.Element(SOAP+"Envelope", nsmap=NS)
    hdr = etree.SubElement(env, SOAP+"Header")
    act = etree.SubElement(hdr, WSA+"Action")
    act.set(SOAP+"mustUnderstand", "true")
    act.text = ACTION
    rt = etree.SubElement(hdr, WSA+"ReplyTo")
    radd = etree.SubElement(rt, WSA+"Address")
    radd.text = replyAddr
    bd = etree.SubElement(env, SOAP+"Body")
    bd.append(body)
    return env

def send_pcc9(server_url, callback_url, pcc9):
    soap = build_soap_msg( etree.fromstring(pcc9), callback_url)
    req = urllib2.Request(server_url)
    req.add_header('content-type',
                   'application/soap+xml;charset=utf-8;action="%s"' % (ACTION,))
    req.add_data(etree.tostring(soap, encoding='utf-8'))
    try:
        fp = urllib2.urlopen(req)
        response = fp.read()
        print 'SUBMITTED PCC-9 AND GOT\n',response
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
        print "I got new PCC-10!! Here it is:"
        print msg
        start_response('200 OK', [('Content-Type', 'text/html')])
        return ["OK"]
    else:
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return ['<h1>Not Found</h1>']

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
          'DICAT']

if __name__ == "__main__":
    parser = OptionParser(usage = "usage: %prog [options]")
    parser.set_defaults(patient_id=PATIENT_ID, provision_code=CARE_PROVISION_CODE, server=SERVER)
    parser.add_option("-p", action="store", dest="patient_id", help='the patient id. Default: %s'%(PATIENT_ID,))
    parser.add_option("-c", action="store", choices=PCODES, dest="provision_code",
                      help='the care provision code (See http://goo.gl/lSMg) Default:%s'%(CARE_PROVISION_CODE,))
    parser.add_option("-s", "--data-source", action="store", dest="server",
                      help='the Data Source endpoint (where the PCC-9 will be send to) Default: %s'%(SERVER,))
    (options, args) = parser.parse_args()

    patient_id = options.patient_id
    provision_code = options.provision_code
    server = options.server
    with open("pcc-9.template.xml") as f:
        pcc9 = f.read()
    pcc9 = pcc9.replace('$PATIENT_ID$', patient_id.replace('&', '&amp;')).replace('$CARE_PROVISION_CODE$', provision_code)
    send_pcc9(server, MYENDPOINT, pcc9)
    print 'I registered (i.e. sent PCC-9) for patient: %s and care prov code: %s' % (patient_id, provision_code)
    print 'Waiting for PCC-10 on %s...' % PORT
    wsgi.WSGIServer(('', PORT), pcc10_handler).serve_forever()
