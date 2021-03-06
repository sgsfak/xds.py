#!/usr/bin/python
from __future__ import with_statement
"""
You probably need to change some Configuration variables you can
find below...

---8<---

Requires:
  * gevent (http://www.gevent.org/)
  * lxml (http://codespeak.net/lxml/)
  * pymongo -- Python driver for MongoDB <http://www.mongodb.org>
"""
__author__ = "Stelios Sfakianakis <ssfak@ics.forth.gr>"
from gevent import monkey; monkey.patch_all()
from gevent import pywsgi
from gevent import Greenlet
from pymongo import json_util
from gevent.event import Event
import gevent
import pymongo
from pymongo import objectid
import bson
import os
import datetime
from lxml import etree
import sys
import urllib2
import json
import uuid
import re
import cgi
import socket
from optparse import OptionParser
import jinja2
# import mongo_utils
from xds_config import *

# See http://goo.gl/NQZX
PCODES_TEMPLATE_IDS = { 'COBSCAT': '1.3.6.1.4.1.19376.1.5.3.1.4.13.2'
                        ,'MEDCCAT': '1.3.6.1.4.1.19376.1.5.3.1.4.5'
                        , 'CONDLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.1'
                        , 'PROBLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.2'
                        , 'INTOLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.3'
                        , 'RISKLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.1'
                        , 'LABCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.13'
                        , 'DICAT':'1.3.6.1.4.1.19376.1.5.3.1.4.13'
                        , 'RXCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'MEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'CURMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'DISCHMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'HISTMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'IMMUCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.12'
                        , 'PSVCCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.19' # XXX
                        , '*':'*' #My extension to get all entries!!
                        }


# A quick (?) way to get (the first of) my IP address
MYIP = socket.gethostbyname_ex(socket.gethostname())[2][0]

# Keep a single instance? It has a thread pool..
MONCON = pymongo.Connection(MONGO_HOST)

def parsePid(patientId):
    delim = '^^^&' # see http://is.gd/fNUSv (search for sourcePatientInfo)
    pid = patientId
    pidroot = ''
    i = patientId.find(delim)
    if i>0:
        pid = patientId[:i]
        i += len(delim)
        j = patientId.find('&ISO', i)
        pidroot = patientId[i:j] if j > 0 else patientId[i:]
    return {'pid':pid, 'root':pidroot}

jinja2_env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))

PCC10_WSA_ACTION = 'urn:hl7-org:v3:QUPC_IN043200UV01'
def create_pcc10(subscription, entries, patientId):
    patId = parsePid(patientId)
    patName = subscription['patientName'] if patId['pid'] != '*' else {'given':'','family':''} # XXX
    entries_xml = [etree.tostring(x, xml_declaration=False) for x in entries]
    template = jinja2_env.get_template('pcc10.xml')
    return template.render(patId=patId, patName=patName,
                           pertInfo=entries_xml, queryId=subscription['queryId'],
                           wsaAction = PCC10_WSA_ACTION, wsaMsgId = uuid.uuid4().urn)

DEFAULT_CARE_MANAGER = 'http://www.example.com:8080/axis2/services/QUPC_AR004030UV_Service'
def send_pcc10(subscription, entries, patientId):
    endpoint = subscription['endpoint_']
    if endpoint is None:
        endpoint = DEFAULT_CARE_MANAGER
    req = urllib2.Request(endpoint)
    req.add_header('content-type',
                   'application/soap+xml;charset=utf-8;action="' + PCC10_WSA_ACTION + '"')
    soap = create_pcc10(subscription, entries, patientId)
    req.add_data(soap.encode('utf-8'))
    # print 'SENDING\n', soap
    try:
        fp = urllib2.urlopen(req)
        response = fp.read()
        # print 'SUBMITTED AND GOT\n',response
    except urllib2.HTTPError, ex:
        msg = ex.read()
        print "PCC10 Error: %s %s" % (ex.code, msg)
        raise ex
    except urllib2.URLError, ex:
        print "PCC10 Error: %s " % (ex.reason)
        raise ex
    except:
        print "PCC10 Unexpected error:", sys.exc_info()[0]
        raise

class SubscriptionLet(Greenlet):
    def __init__(self, subscription, timeout = UB_CHK_TIMEOUT):
        gevent.Greenlet.__init__(self)
        self.subscription = subscription
        self.timeout = timeout
        self._ev = Event()
        self.checking = False
        self.stopped = False
        ## add self to dicts/sets        
        patId = self.subscription['patientId']
        pid = parsePid(patId)['pid']
        workers[self.subscription.get('id')] = self
        if pid == '*':
            workers_per_patient['*'].add(self)
        else:
            workers_per_patient[patId].add(self)

    def subscriptionId(self):
        return self.subscription.get('id')
         
    def __hash__(self):
        return hash(self.subscriptionId())

    def __cmp__(self, other):
        return cmp(self.subscriptionId(), other.subscriptionId())
    
    def wakeup(self):
        self._ev.set()
        
    def stop(self):
        ## remove from dicts/sets
        del workers[self.subscriptionId()]    
        patId = self.subscription['patientId']
        pid = parsePid(patId)['pid']
        if pid == '*':
            workers_per_patient['*'].remove(self)
        else:
            workers_per_patient[patId].remove(self)
        self.stopped = True
        self.wakeup()
        # print "%s committing suicide" % (self,)
        #self.kill()
        
    def match_subscription(self, doc):
        provcode = self.subscription.get('careProvisionCode')
        q = "h:component/h:structuredBody/h:component/h:section/h:entry//*"
        if provcode is not None:
            if provcode != '*':
                q += "[h:templateId/@root='%s']" % PCODES_TEMPLATE_IDS.get(provcode)
            else:
                q = "h:component/h:structuredBody/h:component/h:section//h:entry"
        l = doc.xpath(q, namespaces={'h':'urn:hl7-org:v3'})
        return l

    def check_subscription(self):
        subscription = self.subscription
        sid = self.subscriptionId()
        # print '[%s] Now at subscr' % id, self.subscription
        entries = []
        try:
            docsdb = MONCON.xds.docs
            lastUpdated = subscription['lastChecked_']
            endpoint = subscription.get('endpoint_') or 'http://example.org/'
            patientId = subscription['patientId']
            query = {'mimeType': 'text/xml', 'storedAt_':{'$gt': lastUpdated}}
            pid = parsePid(subscription['patientId'])['pid']
            if pid != '*':
                query['patientId'] = patientId
            careRecordTimePeriod = subscription.get('careRecordTimePeriod')
            # if careRecordTimePeriod is not None:
            #    query['creationTime'] = {'$gte':careRecordTimePeriod['low'], 
            #                             '$lte':careRecordTimePeriod['high']}
            # clinicalStatementTimePeriod = subscription.get('clinicalStatementTimePeriod')
            # if clinicalStatementTimePeriod is not None:
            #    query['creationTime'] = {'$gte':clinicalStatementTimePeriod['low'], 
            #                             '$lte':clinicalStatementTimePeriod['high']}
            print '[%s] MONQ=%s' % (sid, query)
            crs = docsdb.find(query, fields=['filename', 'patientId', 'storedAt_'], 
                              sort=[('storedAt_', pymongo.ASCENDING)])
            tm = None
            for d in crs:
                print '-->', d['filename']
                doc = None
                with open('static'+os.sep+d['filename'], 'rb') as fp:
                    doc = etree.parse(fp).getroot()
                e = self.match_subscription(doc)
                tm = d['storedAt_']
                if len(e) > 0:
                    entries.extend(e)
                    send_pcc10(self.subscription, e, d['patientId'])
                if tm:
                    subscription['lastChecked_'] = tm
                    MONCON.xds.pcc.update({'_id':objectid.ObjectId(sid)},
                                          {"$set": {"lastChecked_": tm}})
            print "[%s] Total Entries Found: %d" % (sid, len(entries))
        finally:
            MONCON.end_request()
        return entries
    
    def __str__(self):
        cpc = self.subscription.get('careProvisionCode')
        if cpc is None:
            cpc = ""
        return "[%s] Subscription {patient: '%s', code:'%s'}" % (self.subscriptionId(),
                                                                 self.subscription['patientId'],
                                                                 cpc)

    def _log_start(self):
        for m in monitors:
            m.started(self.subscriptionId(), sub_to_dict(self.subscription))
    def _log_finish(self):
        for m in monitors:
            m.finished(self.subscriptionId())
    def _log_start_checking(self):
        self.checking = True
        for m in monitors:
            m.check_started(self.subscriptionId())
    def _log_finish_checking(self):
        self.checking = False
        for m in monitors:
            m.check_finished(self.subscriptionId(), tm_to_iso(self.subscription['lastChecked_']))
        
    def _run(self):
        sid = self.subscriptionId()
        print "[%s] SubscriptionLet starting.." % sid
        self._log_start()
        while True:
            try:
                self._log_start_checking()
                self.check_subscription()
            except Exception, ex:
                print "[%s] Oh no! just got: %s" % (sid, ex)
                raise
            finally:
                self._log_finish_checking()
                print "[%s] Going to sleep for %d secs ..." % (sid, self.timeout)
                op = self._ev.wait(timeout=self.timeout)    
                if op:
                    self._ev.clear()
                    if self.stopped :
                        break
        self._log_finish()
        print "%s ending.." % (self,)
        self.kill() # ???
workers = {}
from collections import defaultdict
workers_per_patient = defaultdict(set)

monitors = set()

def handle_notification(conn, addr):
    bufsize = 4096
    data = conn.recv(bufsize)
    # BSON provides the length of the msg in int32 litle-endian
    import struct
    ln = struct.unpack("<i", data[:4])[0]
    # print "len=%d expecting %s" % (len(data), ln)
    while len(data) < ln:
        data += conn.recv(bufsize)
    conn.close()
    msg = bson.BSON(data).decode()
    sub = msg.get('payload', '')
    op = msg.get('type', 'noop')
    if op == 'subscription':
        subid = sub['id']
        print '****** Got New subscription:', sub
        if workers.has_key(subid):
            return
        g = SubscriptionLet(sub)
        g.start()
    elif op == 'submission':
        patId = sub['patientId']
        print "****** Got New submission set for patient='%s'" % patId
        for g in workers_per_patient.get(patId, set()):
            g.wakeup()
        for g in workers_per_patient.get('*', set()):
            g.wakeup()

def listen_for_new_info(port):
    from gevent.server import StreamServer
    server = StreamServer(('127.0.0.1', port), handle_notification)
    server.start() # start accepting new connections

def schedule_all(timeout, notify_port, modulo=0, m=1):
    """Create the worker threads for the currently available PCC-9 subscriptions"""
    print 'Registering workers per PCC-9 subscription...'
    import random
    random.seed(47)
    if timeout < 60:
        timeout = 60
    try:
        pcc = MONCON.xds.pcc
        k = 0
        for i in pcc.find(sort=[('storedAt_', pymongo.ASCENDING)]):
            if k % m == modulo:
                i['id'] = str(i.get('_id'))
                del i['_id']
                period = timeout + random.randint(-30, 29) 
                g = SubscriptionLet(i, period)
                g.start()
            k = k + 1
    except Exception, e:
        print 'Exception....' + str(e)
    finally:
        MONCON.end_request()
        print 'Registering %d workers ended' % (len(workers),)
        # gevent.joinall(workers)
    if notify_port > 0:
        listen_for_new_info(notify_port)

def tm_to_iso(tm):
    return datetime.datetime.fromtimestamp(tm).isoformat(' ')
def sub_to_dict(w):
    dct = w
    dct['lastDoc'] = tm_to_iso(w['lastChecked_'])
    dct['storedAt'] = tm_to_iso(w['storedAt_'])
    dct['endpoint'] = w['endpoint_']
    return dct
def get_stats(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/html;charset=utf-8')])
    template = jinja2_env.get_template('ub_monitor.html')
    return [template.render(subs=[sub_to_dict(i.subscription) for k, i in workers.items()]) ]

def realtime_monitor(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/event-stream'),
                              ('Cache-Control', 'no-cache')])
    import gevent.queue
    class Monitor:
        def __init__(self):
            global monitors
            self.q_ = gevent.queue.Queue()
            self.stopped_ = False
            self.first_ = True
            monitors.add(self)
            print "Monitor %s started.." % (hash(self))
        def started(self, sid, sub):
            self.q_.put({'op': 'started', 'sid':sid, 'sub':sub})
        def finished(self, sid):
            self.q_.put({'op': 'finished', 'sid':sid})
        def check_started(self, sid):
            self.q_.put({'op': 'active', 'sid':sid})
        def check_finished(self, sid, lastDoc):
            self.q_.put({'op': 'inactive', 'sid':sid, 'lastDoc':lastDoc})
        def __hash__(self):
            return hash(self.q_)
        def __iter__(self):
            return self
        def close(self):
            global monitors
            monitors.remove(self)
            print "Monitor %s ended.." % (hash(self))
        def next(self):
            if self.stopped_:
                raise StopIteration()
            if self.first_:
                self.first_ = False
                return '\n\n'
            try:
                w = self.q_.get(timeout=3*60);
            except gevent.queue.Empty:
                self.stopped_ = True
                raise StopIteration()
            return 'data: ' + json.dumps(w) + '\n\n'
    return Monitor()
                    
        
def subscription_resource(subId, env, start_response):
    if not workers.has_key(subId):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return ['<h1>Not Found</h1><p> Subscription: %s was not found' % subId]
    method = env['REQUEST_METHOD'].upper()
    nonREST = False
    if method == 'POST' and env.has_key('HTTP_X_HTTP_METHOD_OVERRIDE'):
        method = env['HTTP_X_HTTP_METHOD_OVERRIDE'].upper()
    if method == 'POST' and env.get('CONTENT_TYPE', '') == 'application/x-www-form-urlencoded':
        request_body = env['wsgi.input'].read()
        d = cgi.parse_qs(request_body)
        method = d.get('method', ['POST'])[0].upper()
        nonREST = True
    try:
        oid = pymongo.objectid.ObjectId(subId)
        pcc = MONCON.xds.pcc
        if method == 'GET':
            s = pcc.find_one(oid)
            if not s:
                start_response('404 Not Found', [('Content-Type', 'text/html')])
                return ['<h1>Not Found</h1><p> Subscription: %s was not found' % subId]
            s['_id'] = str(s['_id'])
            start_response('200 OK', [('Content-Type', 'text/plain;charset=utf-8')])
            return [json.dumps(s, default=json_util.default, sort_keys=True, indent=4)]
        elif method == 'DELETE':
            status = pcc.remove(oid, safe=True)
            # print status
            if status['err'] is not None:
                start_response('500 Internal server error', [('Content-Type', 'text/html')])
                return ['<h1>Internal server Error</h1> <pre>%s</pre>' % status['err']]
            else:
                w = workers[subId]
                w.stop()
                if nonREST:
                    start_response('303 See other', [('Location', '/')])
                else:
                    start_response('200 OK', [('Content-Type', 'text/html;charset=utf-8')])
                return []
        else:
            start_response('405 Method not allowed', [('Content-Type', 'text/html')])
            return ['<h1>Method is not allowed</h1>']
    except Exception, e:
        print 'Exception....' + str(e)
        start_response('500 Internal server error', [('Content-Type', 'text/html')])
        return ['<h1>Internal server Error</h1> <pre>%s</pre>' % str(e)]
    finally:
        MONCON.end_request()
        
        

REST_RE = re.compile('\A/subscription/(\w+)\Z')
def application(env, start_response):
    path = env['PATH_INFO'] or '/'
    if path in ['/', '/subscription/']:
        return get_stats(env, start_response)
    if path == '/monitor':
        return realtime_monitor(env, start_response)
    m = REST_RE.match(path)
    if not m:
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return ['<h1>Not Found</h1>']
    sid = m.group(1)
    return subscription_resource(sid, env, start_response)

def test_event():
    if len(workers) > 0:
        print "waking up..."
        workers.items()[0][1].wakeup()

def parse_options():
    parser = OptionParser(usage = "usage: %prog [options]")
    parser.set_defaults(port = UB_LISTEN_PORT, notify_port=None, timeout = UB_CHK_TIMEOUT, k=0, mod=1)
    parser.add_option("-p", "--http", action="store", dest="port", type="int",
                      help='The TCP port to listen to for the HTTP interface. Default: %s'% UB_LISTEN_PORT)
    parser.add_option("-n", action="store", dest="notify_port", type="int",
                      help='The TCP port to listen to for the communication with XDS. Use 0 to deactivate. Default: UB_LISTEN_PORT + 1')
    parser.add_option("-t", action="store", dest="timeout", type="int",
                      help='Timeout in seconds to be used for the periodic check of subscriptions. Default: %s (i.e. %s minutes)'%
                      (UB_CHK_TIMEOUT, UB_CHK_TIMEOUT/60))
    parser.add_option("-m", action="store", dest="mod", type="int",
                      help='Divisor the # of subscriptions. Default: 1')
    parser.add_option("-k", action="store", dest="k", type="int",
                      help='Remainder. Default: 0')
    (options, args) = parser.parse_args()
    options.k = options.k % options.mod
    # print options.k,options.mod
    if options.notify_port is None:
        options.notify_port = options.port+1
    return options

def main():
    options = parse_options()
    s = pywsgi.WSGIServer(('', options.port), application)
    s.start()
    gevent.spawn(schedule_all, options.timeout, options.notify_port, modulo=options.k, m=options.mod)
    print 'Admin/monitor interface at http://%s:%s/' % (MYIP, options.port)
    print 'Notification listening port: %s' % options.notify_port
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print 'Exiting...'
        s.stop()

if __name__ == "__main__":
    main()
