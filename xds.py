#!/usr/bin/python
from __future__ import with_statement
"""
This is a small XDS.b IHE compliant REgistry and Repository server
The Repository is actually the filesystem (the static directory)
while the Registry stores the documents and submission sets metadata
in a MongoDB json database server.

You probably need to checnge some Configuration variables you can
find below...

---8<---

Requires:
  * web.py (http://webpy.org)
  * lxml (http://codespeak.net/lxml/)
  * pymongo -- Python driver for MongoDB <http://www.mongodb.org>
"""
__author__ = "Stelios Sfakianakis <ssfak@ics.forth.gr>"

import web
import email
import uuid
from lxml import etree
import pymongo
import hashlib

# Configuration!!
MY_REPO_ID= "1.1.1.1.1"
MONGO_HOST = "139.91.190.45"

NS = {"soap":"http://www.w3.org/2003/05/soap-envelope", 
      "wsa":"http://www.w3.org/2005/08/addressing",
      "xdsb":"urn:ihe:iti:xds-b:2007",
      "rs":"urn:oasis:names:tc:ebxml-regrep:xsd:rs:3.0",
      "lcm":"urn:oasis:names:tc:ebxml-regrep:xsd:lcm:3.0",
      "rim":"urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0",
      "query":"urn:oasis:names:tc:ebxml-regrep:xsd:query:3.0",
      "xop":"http://www.w3.org/2004/08/xop/include"}

# The actions for the supported XDS transactions
PNR_XDS_OP = 'urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b'
SQ_XDS_OP = 'urn:ihe:iti:2007:RegistryStoredQuery'
RETR_XDS_OP = 'urn:ihe:iti:2007:RetrieveDocumentSet'

# PnR Submission Set 
# (see <http://goo.gl/mppj>)
SSET_CLASS_NODE = "urn:uuid:a54d6aa5-d40d-43f9-88c5-b4633d873bdd"
AUTHOR_SSET_CLASS = "urn:uuid:a7058bb9-b4e4-4307-ba5b-e3f0ab85e12d"
CT_SSET_CLASS = "urn:uuid:aa543740-bdda-424e-8c96-df4873be8500"

# Identification schemes UUIDs
# See also <http://goo.gl/8lfE>
UNIQID_SSET_SCHEME = "urn:uuid:96fdda7c-d067-4183-912e-bf5ee74998a8"
SRCID_SSET_SCHEME = "urn:uuid:554ac39e-e3fe-47fe-b233-965d2a147832"
PATID_SSET_SCHEME = "urn:uuid:6b5aea1a-874d-4603-a4bc-96a0a7b38446"

CLASSIFICATION_OBJTYPE = 'urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:Classification'
EXTERNID_OBJTYPE = 'urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:ExternalIdentifier'
REGPACKGE_OBJTYPE = "urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:RegistryPackage"

# For document entries
DOC_OBJTYPE = "urn:uuid:7edca82f-054d-47f2-a032-9b2a5b5186c1"
CLCODE_DOC_CLASS = "urn:uuid:41a5887f-8865-4c09-adf7-e362475b143a"
AUTHOR_DOC_CLASS = "urn:uuid:93606bcf-9494-43ec-9b4e-a7748d1a838d"
CONFCODE_DOC_CLASS = "urn:uuid:f4f85eac-e6cb-4883-b524-f2705394840f"
EVCODE_DOC_CLASS = "urn:uuid:2c6b8cb7-8b2a-4051-b291-b1ae6a575ef4"
FMTCODE_DOC_CLASS = "urn:uuid:a09d5840-386c-46f2-b5ad-9c3699a4309d"
HCTC_DOC_CLASS = "urn:uuid:f33fb8ac-18af-42cc-ae0e-ed0b0bdb91e1"
PRCTC_DOC_CLASS = "urn:uuid:cccf5598-8b07-4b77-a05e-ae952c785ead"
TC_DOC_CLASS = "urn:uuid:f0306f51-975f-434e-a61c-c59651d33983"

PATID_DOC_SCHEME = "urn:uuid:58a6f841-87b3-4a3e-92fd-a8ffeff98427"
UNIQID_DOC_SCHEME = "urn:uuid:2e82c1f6-a085-4c72-9da3-8640a32e42ab"

# For Folders
FLD_OBJTYPE = "urn:uuid:d9d542f3-6cc4-48b6-8870-ea235fbc94c2"
CODEL_FLD_CLASS = "urn:uuid:1ba97051-7806-41a8-a48b-8fce7af683c5"
PATID_FLD_SCHEME = "urn:uuid:f64ffdf0-4b97-4e06-b79f-a52b38ec2f8a"
UNIQID_FLD_SCHEME = "urn:uuid:75df8f67-9973-4fbe-a900-df66cefecc5a"

#For Relationships
APND_CLASS = "urn:uuid:917dc511-f7da-4417-8664-de25b34d3def"
RPLC_CLASS = "urn:uuid:60fd13eb-b8f6-4f11-8f28-9ee000184339"
XFRM_CLASS = "urn:uuid:ede379e6-1147-4374-a943-8fcdcf1cd620"
XFRM_RPLC_CLASS = "urn:uuid:b76a27c7-af3c-4319-ba4c-b90c1dc45408"
SIGNS_CLASS = "urn:uuid:8ea93462-ad05-4cdc-8e54-a8084f6aff94"

HASMEM_ASSOCTYPE = "urn:oasis:names:tc:ebxml-regrep:AssociationType:HasMember"
RPLC_ASSOCTYPE = "urn:ihe:iti:2007:AssociationType:RPLC"

def get_author(xml, scheme, obj):
        def cons_auth(class_xml):
                auth = {}
                auth['authorPerson'] = get_slot_single(class_xml, 'authorPerson')
                auth['authorInstitution'] =  get_slot_multi(class_xml, 'authorInstitution')
                auth['authorRole'] = get_slot_multi(class_xml, 'authorRole')
                auth['authorSpecialty'] = get_slot_multi(class_xml, 'authorSpecialty')
                return auth
        l = xml.xpath("//rim:Classification[@classificationScheme='%s' and @classifiedObject='%s']"%
                      (scheme, obj), namespaces=NS)
        if len(l)==0: return None
        return [cons_auth(class_xml) for class_xml in l]

def get_classification_multi(xml, scheme, obj):
        def cons_code(c):
                (cs,) = c.xpath("rim:Slot[@name='codingScheme']/rim:ValueList/rim:Value", namespaces=NS)
                cd = c.attrib['nodeRepresentation']
                return {"codingScheme":cs.text, "code":cd}
        l = xml.xpath("//rim:Classification[@classificationScheme='%s' and @classifiedObject='%s']"%
                (scheme, obj), namespaces=NS)
        return [cons_code(i) for i in l]

def xml_authors(xml, scheme, authrs, clObj):
        RIM = "{%s}" % NS['rim']
        authors = type(authrs) == list and authrs or [authrs]
        for author in authors:
                c  = etree.SubElement(xml, RIM+"Classification",
                        attrib={'id': uuid.uuid4().urn, 
                                'objectType':CLASSIFICATION_OBJTYPE,
                                'classificationScheme': scheme,
                                'classifiedObject': clObj,
                                'nodeRepresentation':'',
                                'home':''
                                })
                for k in author.keys():
                        xml_slot(c, k, author[k])
                n = etree.SubElement(c, RIM+"Name")
                d = etree.SubElement(c, RIM+"Description")
                v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})

def xml_slot(xml, name, values):
        if values is None: return
        RIM = "{%s}" % NS['rim']
        s = etree.SubElement(xml, RIM+"Slot", attrib={'name':name})
        vl = etree.SubElement(s, RIM+"ValueList")
        vs = type(values) == list and values or [values]
        for v in vs:
                vt = etree.SubElement(vl, RIM+"Value")
                vt.text = "%s"%v

def xml_classification(xml, scheme, codes, clObj):
        if codes is None: return
        RIM = "{%s}" % NS['rim']
        cds = type(codes)==list and codes or [codes]
        for coded in cds:
                c  = etree.SubElement(xml, RIM+"Classification",
                        attrib={'id': uuid.uuid4().urn,
                                'objectType':CLASSIFICATION_OBJTYPE,
                                'classificationScheme': scheme,
                                'classifiedObject': clObj,
                                'nodeRepresentation':coded['code'],
                                'home':''
                                })
                xml_slot(c, 'codingScheme', coded['codingScheme'])
                n = etree.SubElement(c, RIM+"Name")
                d = etree.SubElement(c, RIM+"Description")
                v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})

def xml_external_id(xml, scheme, name, value, idObj):
        if value is None: return
        RIM = "{%s}" % NS['rim']
        c  = etree.SubElement(xml, RIM+"ExternalIdentifier",
                        attrib={'id': uuid.uuid4().urn,
                                'objectType':EXTERNID_OBJTYPE,
                                'identificationScheme':scheme,
                                'value':value,
                                'registryObject':idObj,
                                'home':''
                                })
        n = etree.SubElement(c, RIM+"Name")
        l=etree.SubElement(n, RIM+"LocalizedString", 
                           attrib={'{http://www.w3.org/XML/1998/namespace}lang':'en-US',
                                   'value':name})
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})


def xml_document(xml, doc):
        RIM = "{%s}" % NS['rim']
        def add_slots(xml, nms):
                for n in nms:
                        if n in doc: xml_slot(xml, n, doc[n])
        id = doc['entryUUID']
        c  = etree.SubElement(xml, RIM+"ExtrinsicObject",
                        attrib={'id': id,
                                'objectType':DOC_OBJTYPE,
                                'status':'urn:oasis:names:tc:ebxml-regrep:StatusType:'+doc.get('availabilityStatus'),
                                'mimeType':doc['mimeType'],
                                'isOpaque':'false',
                                'home':''
                                })
        add_slots(c, ['availabilityStatus', 'URI', 'creationTime', 'hash', 'languageCode', 
                        'repositoryUniqueId','serviceStartTime','serviceStopTime'
                        ,'size', 'sourcePatientId', 'sourcePatientInfo'
                        ,'legalAuthenticator'])
        n = etree.SubElement(c, RIM+"Name")
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_authors(c, AUTHOR_DOC_CLASS, doc.get('author'), id) 
        xml_classification(c, CLCODE_DOC_CLASS, doc.get('classCode'), id)
        xml_classification(c, EVCODE_DOC_CLASS, doc.get('formatCode'), id)
        xml_classification(c, HCTC_DOC_CLASS, doc.get('healthcareFacilityTypeCode'), id)
        xml_classification(c, PRCTC_DOC_CLASS, doc.get('practiceSettingCode'), id)
        
        xml_external_id(c, PATID_DOC_SCHEME, 'XDSDocumentEntry.patientId', doc['patientId'], id)
        xml_external_id(c, UNIQID_DOC_SCHEME, 'XDSDocumentEntry.uniqueId', doc['uniqueId'], id)

def xml_submission(xml, doc):
        RIM = "{%s}" % NS['rim']
        def add_slots(xml, nms):
                for n in nms:
                        if n in doc: xml_slot(xml, n, doc[n])
        id = doc['entryUUID']
        c  = etree.SubElement(xml, RIM+"RegistryPackage",
                        attrib={'id': id,
                                'objectType':REGPACKGE_OBJTYPE,
                                'status':'urn:oasis:names:tc:ebxml-regrep:StatusType:Approved'
                                })
        add_slots(c, ['submissionTime', 'intendedRecipient'])
        n = etree.SubElement(c, RIM+"Name")
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_authors(c, AUTHOR_SSET_CLASS, doc.get('author'), id) 
        xml_classification(c, CT_SSET_CLASS, doc.get('contentTypeCode'), id)
        cc  = etree.SubElement(c, RIM+"Classification",
                              attrib={'id': uuid.uuid4().urn,
                                      'objectType':CLASSIFICATION_OBJTYPE,
                                      'classifiedObject': id,
                                      'classificationNode':"urn:uuid:a54d6aa5-d40d-43f9-88c5-b4633d873bdd"
                                      })
        n = etree.SubElement(cc, RIM+"Name")
        d = etree.SubElement(cc, RIM+"Description")
        v = etree.SubElement(cc, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_external_id(c, PATID_SSET_SCHEME, 'XDSSubmissionSet.patientId', doc['patientId'], id)
        xml_external_id(c, UNIQID_SSET_SCHEME, 'XDSSubmissionSet.uniqueId', doc['uniqueId'], id)
        xml_external_id(c, SRCID_SSET_SCHEME, 'XDSSubmissionSet.sourceId', doc['sourceId'], id)

def get_classification(xml, scheme, obj):
        l = get_classification_multi(xml, scheme, obj)
        if len(l)==0: return None
        return l[0]

def get_external_id(xml, scheme, obj):
        l = xml.xpath("//rim:ExternalIdentifier[@identificationScheme='%s' and @registryObject='%s']"%
                (scheme, obj), namespaces=NS)
        if len(l)==0: return None
        (c,) = l
        return c.attrib['value']

def get_slots(o):
        sl = {}
        for s in o.xpath("rim:Slot", namespaces=NS):
                sl[s.attrib["name"]] = [v.text for v in s.xpath("rim:ValueList/rim:Value", namespaces=NS)]
        return sl

def get_slot_multi(o, name):
        vls = o.xpath("rim:Slot[@name='%s']/rim:ValueList/rim:Value"% name, 
                      namespaces=NS)
        return [v.text for v in vls]

def get_slot_single(o, name):
        vls = get_slot_multi(o, name)
        if len(vls) > 0: return vls[0]
        return None

def parse_provide_and_register(xml):
        (cl, ) = xml.xpath("//lcm:SubmitObjectsRequest/rim:RegistryObjectList/rim:Classification[@classificationNode='%s']"%SSET_CLASS_NODE, namespaces=NS)
        sId = cl.get("classifiedObject")
        (rp, ) = xml.xpath("//rim:RegistryPackage[@id='%s']" % sId, namespaces=NS)
        sUUID = sId
        if not sUUID.startswith("urn:uuid:"): sUUID = uuid.uuid4().urn
        sset = {}
        sset["entryUUID"] = sUUID
        sset["submissionTime"] = get_slot_single(rp, "submissionTime")
        sset["intendedRecipient"] = get_slot_multi(rp, "intendedRecipient")
        f = get_external_id(xml, UNIQID_SSET_SCHEME, sId)
        sset["uniqueId"] = f
        f = get_author(xml, AUTHOR_SSET_CLASS, sId)
        if f: sset["author"] = f
        f = get_classification(xml, CT_SSET_CLASS, sId)
        if f: sset["contentTypeCode"] = f
        f = get_external_id(xml, PATID_SSET_SCHEME, sId)
        sset["patientId"] = f
        f = get_external_id(xml, SRCID_SSET_SCHEME, sId)
        sset["sourceId"] = f
        members = xml.xpath("//rim:Association[@associationType='%s' and @sourceObject='%s']/@targetObject" % 
                            (HASMEM_ASSOCTYPE, sId), namespaces=NS)
        sset["docs"] = {}
        for dId in members:
                l = xml.xpath("//rim:ExtrinsicObject[@id='%s']"%dId, namespaces=NS)
                if l is None or len(l)==0: continue
                eo = l[0]
                (cid,) = xml.xpath("//xdsb:Document[@id='%s']/xop:Include/@href" % dId, namespaces=NS)
                cid = "<%s>" % cid[4:]
                docen = {}
                docen["availabilityStatus"]="Approved"
                f = get_author(xml, AUTHOR_DOC_CLASS, dId)
                if f: docen["author"] = f
                f = get_classification(xml, CLCODE_DOC_CLASS, dId)
                if f: docen["classCode"] = f
                f = get_slot_single(eo, "creationTime")
                if f: docen["creationTime"] = f
                dUUID = dId
                if not dUUID.startswith("urn:uuid:"): dUUID = uuid.uuid4().urn
                docen["entryUUID"] = dUUID
                docen["eventCodeList"] = get_classification_multi(xml, EVCODE_DOC_CLASS, dId)
                f = get_classification(xml, FMTCODE_DOC_CLASS, dId)
                if f: docen["formatCode"] = f
                f = get_classification(xml, HCTC_DOC_CLASS, dId)
                if f: docen["healthcareFacilityTypeCode"] = f
                f = get_slot_single(eo, "languageCode")
                if f: docen["languageCode"] = f
                f = get_slot_single(eo, "legalAuthenticator")
                if f: docen["legalAuthenticator"] = f
                docen["mimeType"] = eo.get("mimeType")
                docen["patientId"] = get_external_id(xml, PATID_DOC_SCHEME, dId)
                f = get_classification(xml, PRCTC_DOC_CLASS, dId)
                if f: docen["practiceSettingCode"] = f
                docen["repositoryUniqueId"] = MY_REPO_ID
                f = get_slot_single(eo, "serviceStartTime")
                if f: docen["serviceStartTime"] = f
                f = get_slot_single(eo, "serviceStopTime")
                if f: docen["serviceStopTime"] = f
                f = get_slot_single(eo, "size")
                if f: docen["size"] = f
                f = get_slot_single(eo, "sourcePatientId")
                if f: docen["sourcePatientId"] = f
                docen["sourcePatientInfo"] = get_slot_multi(eo, "sourcePatientInfo")
                docen["typeCode"] = get_classification(xml, TC_DOC_CLASS, dId)
                docen["uniqueId"] = get_external_id(xml, UNIQID_DOC_SCHEME, dId)
                docen["filename"] = dUUID[9:] + guess_suffix(docen['mimeType'])
                docen["URI"] = "/xdsdocs/" + docen["filename"]
                docen["inSubmissionUUID"] = sUUID
                sset["docs"][cid] = docen
        return sset

SUFFIXES_FOR_TYPES = {
        'application/pdf': 'pdf',
        'text/xml': 'xml',
        'text/html': 'html',
        'text/plain': 'txt',
        'application/xml': 'xml',
        'application/xhtml': 'xhtml',
        'image/gif' : 'gif',
        'image/png' : 'png',
        'image/jpeg' : 'jpg'
}
def guess_suffix(ct):
    if ct in SUFFIXES_FOR_TYPES: return "."+SUFFIXES_FOR_TYPES[ct]
    return ''

def parse_content_type(ct):
        s = "content_type="+ct
        v = [t.strip() for t in s.split(';')]
        return dict([tuple(l.split('=')) for l in v])

SUCCESS_RESULT_STATUS = "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Success"

def handle_mtom_oper(msg):
        from lxml import etree
        msgs = msg.get_payload()
        xml = msgs[0].get_payload()
        root = etree.fromstring(xml)
        wact = root.xpath("/soap:Envelope/soap:Header/wsa:Action", 
                          namespaces=NS)[0]
        wmesgid = root.xpath("/soap:Envelope/soap:Header/wsa:MessageID", 
                             namespaces=NS)[0].text
        oper = wact.text
        resAct = oper + "Response"
        (body,) = root.xpath("/soap:Envelope/soap:Body", namespaces=NS)
        print "---> TRANSACTION: " , oper[oper.rfind(':')+1:]
        if oper == PNR_XDS_OP:#w is not None:
                sset = parse_provide_and_register(body)
                docs = sset["docs"]
                sset["docs"] = []
                con = pymongo.Connection(host=MONGO_HOST)
                for m in msgs[1:]:
                        cid = m['Content-ID']
                        doc = docs[cid]
                        fn  = doc["filename"]
                        data = m.get_payload(decode=True)
                        with open("static/"+fn, "wb") as fp:
                                fp.write(data)
                                doc["size"] = fp.tell()
                        print "wrote ", fn
                        doc["hash"] = hashlib.sha1(data).hexdigest()
                        con.xds.docs.insert(doc)
                        sset['docs'].append(doc['entryUUID'])
                        print 'Document',doc['entryUUID'], 'inserted'
                con.xds.ssets.insert(sset)
                print 'submission',sset['entryUUID'], 'inserted'
                con.disconnect()
                RS = NS['rs']
                res = etree.Element("{%s}RegistryResponse" % RS)
                res.attrib['status'] = SUCCESS_RESULT_STATUS
                soapMsg = build_soap_msg(resAct, wmesgid, res)
                ret = generate_mtom(soapMsg, resAct)
                #print ret
                return ret
        elif oper == RETR_XDS_OP:
                elems = body.xpath("xdsb:RetrieveDocumentSetRequest/xdsb:DocumentRequest/xdsb:DocumentUniqueId", namespaces=NS)
                docUids = [e.text for e in elems]
                print docUids
                toRetrieve = []
                con = pymongo.Connection(host=MONGO_HOST)
                from email.utils import make_msgid
                for uid in docUids:
                        doc = con.xds.docs.find_one({"uniqueId": uid}, {"filename":1, "mimeType":1})
                        if not doc:
                                print "Requested doc with uid ",uid, " was not found! (ignoring)"
                        else:
                                cid = make_msgid()
                                toRetrieve.append({"uid":uid, 
                                                   "fn":doc['filename'], 
                                                   "cid":cid, 
                                                   "mt":doc['mimeType']})
                con.disconnect()
                RS = NS['rs']
                XDSB = NS['xdsb']
                res = etree.Element("{%s}RetrieveDocumentSetResponse" % XDSB)
                rr = etree.Element(res,"{%s}RegistryResponse" % RS)
                rr.attrib['status'] = SUCCESS_RESULT_STATUS
                for tr in toRetrieve:
                        e = etree.Element(res,"{%s}DocumentResponse"%(XDSB,))
                        e1 = etree.Element(e, "{%s}RepositoryUniqueId"%(XDSB,))
                        e1.text = MY_REPO
                        e2 = etree.Element(e, "{%s}DocumentUniqueId"%(XDSB,))
                        e2.text = tr['uid']
                        e3 = etree.Element(e, "{%s}mimeType"%(XDSB,))
                        e3.text = tr['mt']
                        d = etree.Element(e, "{%s}Document"%(XDSB,))
                        x = etree.Element(d, "{%s}Include"%(NS['xop'],))
                        x.attrib['href']="cid:"+tr['cid']
                soapMsg = build_soap_msg(resAct, wmesgid, res)
                ret = generate_mtom(soapMsg, resAct, toRetrieve)
                #print ret
                return ret
        return None 

def build_soap_msg(action, relMsg, body):
        SOAP = "{%s}" % NS['soap']
        WSA = "{%s}" % NS['wsa']
        env = etree.Element(SOAP+"Envelope", nsmap=NS)
        hdr = etree.SubElement(env, SOAP+"Header")
        act = etree.SubElement(hdr, WSA+"Action")
        act.text = action
        rel = etree.SubElement(hdr, WSA+"RelatesTo")
        rel.text = relMsg
        bd = etree.SubElement(env, SOAP+"Body")
        bd.append(body)
        return env
        
def generate_mtom(xml_part, resAct, docs=[]):
        result = etree.tostring(xml_part, pretty_print=True, 
                                encoding='UTF-8',
                                #encoding='ISO-8859-1',
                                xml_declaration=True)
        from email.utils import make_msgid
        cid = make_msgid()
        boundary = "===============5s1t9e5l8i3o0s6r4u8l1e6s1.6.2.1.2.8=="
        mtom_ct = "multipart/related; action=\"%s\"; start-info=\"application/soap+xml\"; type=\"application/xop+xml\"; start=\"%s\";boundary=\"%s\"" % (resAct, cid, boundary)
        web.header('Content-Type', mtom_ct)
        from cStringIO import StringIO
        out = StringIO()
        out.write("--%s\r\n" % boundary)
        out.write('Content-Type: application/xop+xml;type="application/soap+xml"\r\n')
        out.write('Content-Transfer-Encoding: binary\r\n')
        out.write("Content-ID: %s\r\n\r\n" % cid)
        out.write(result)
        for d in docs:
                out.write("\r\n--%s\r\n" % boundary)
                data = out.getvalue()
                out.close()
                yield data
                out = StringIO()
                out.write('Content-Type: application/octet-stream\r\n')
                out.write('Content-Transfer-Encoding: binary\r\n')
                out.write("Content-ID: %s\r\n\r\n" % d['cid'])
                with open(d['fn'], 'rb') as fp:
                        buf = fp.read(8*1024)
                        while not buf == '':
                                out.write(buf)
                                data = out.getvalue()
                                out.close()
                                yield data
                                out = StringIO()
                                buf = fp.read(8*1024)
        
        out.write("\r\n--%s--" % boundary)
        data = out.getvalue()
        out.close()
        yield data

FINDDOCUMENTS_SQ = "urn:uuid:14d4debf-8f97-4251-9a74-a90016b0af0d"
FINDSUBMISSIONSETS_SQ = "urn:uuid:f26abbcb-ac74-4422-8a30-edb644bbc1a9"
FINDFOLDERS_SQ = "urn:uuid:958f3006-baad-4929-a4de-ff1114824431"
GETALL_SQ = "urn:uuid:10b545ea-725c-446d-9b95-8aeb444eddf3"
GETDOCUMENTS_SQ = "urn:uuid:5c4f972b-d56b-40ac-a5fc-c8ca9b40b9d4"
GETFOLDERS_SQ = "urn:uuid:5737b14c-8a1a-4539-b659-e03a34a5e1e4"
GETASSOCIATIONS_SQ = "urn:uuid:a7ae438b-4bc2-4642-93e9-be891f7bb155"
GETDOCUMENTSANDASSOCIATIONS_SQ = "urn:uuid:bab9529a-4a10-40b3-a01f-f68a615d247a"
GETSUBMISSIONSETS_SQ = "urn:uuid:51224314-5390-4169-9b91-b1980040715a"
GETSUBMISSIONSETANDCONTENTS_SQ = "urn:uuid:e8e3cb2c-e39c-46b9-99e4-c12f57260b83"
GETFOLDERANDCONTENTS_SQ = "urn:uuid:b909a503-523d-4517-8acf-8e5834dfc4c7"
GETFOLDERSFORDOCUMENT_SQ = "urn:uuid:10cae35a-c7f9-4cf5-b61e-fc3278ffb578"
GETRELATEDDOCUMENTS_SQ = "urn:uuid:d90e5407-b356-4d91-a89f-873917b4b0e6"

def handle_simple_soap_oper(inp):
        root = etree.fromstring(inp)
        wact = root.xpath("/soap:Envelope/soap:Header/wsa:Action", 
                          namespaces=NS)[0]
        wmesgid = root.xpath("/soap:Envelope/soap:Header/wsa:MessageID", 
                             namespaces=NS)[0].text
        oper = wact.text
        resAct = oper + "Response"
        print '--> SO I got ', oper
        q = root.xpath("//query:AdhocQueryRequest", namespaces=NS)[0]
        refsOnly = q.xpath("query:ResponseOption/@returnType", 
                           namespaces=NS)[0] == 'ObjectRef'
        monSel = None
        if refsOnly: monSel=['entryUUID']
        sq = q.xpath("rim:AdhocQuery/@id", namespaces=NS)[0]
        if sq not in [GETDOCUMENTS_SQ, GETDOCUMENTSANDASSOCIATIONS_SQ, 
                        GETSUBMISSIONSETANDCONTENTS_SQ, FINDDOCUMENTS_SQ,
                        FINDSUBMISSIONSETS_SQ]:
                print "Sorry I don't support this (",sq,") type of query!"
        else:
                crit = {}
                for st in q.xpath("rim:AdhocQuery/rim:Slot", namespaces=NS):
                        n = st.attrib['name']
                        crit[n] = []
                        for vt in st.xpath("rim:ValueList/rim:Value",  namespaces=NS):
                                v = vt.text.strip()
                                if v.startswith('('):
                                        v = v[1:-1] # remove ( and )
                                        for a in v.strip().split(','):
                                                crit[n].append(a.strip().strip("'"))
                                else:
                                        crit[n].append(v.strip().strip("'"))
                print "CRITERIA : ", crit
                searchSubmissions = sq == GETSUBMISSIONSETANDCONTENTS_SQ or sq == FINDSUBMISSIONSETS_SQ
                monqry = {}
                for k,v in crit.items():
                        if k.endswith('UniqueId'):
                                monqry['uniqueId']= len(v)==1 and v[0] or {"$in":v}
                        elif k.endswith('EntryUUID'):
                                monqry['entryUUID']=len(v)==1 and v[0] or {"$in":v}
                        elif k.endswith('Status'):
                                monqry['availabilityStatus']=v[0][v[0].rfind(':')+1 :]
                        elif k.endswith('PatientId'):
                                monqry['patientId']=v[0]
                print "MONGO QUERY: ", monqry
                con = pymongo.Connection(MONGO_HOST)
                coll = searchSubmissions and con.xds.ssets or con.xds.docs
                QNS = "{%s}" % NS['query']
                RIM = "{%s}" % NS['rim']
                xml = etree.Element(QNS+"AdhocQueryResponse")
                xml.attrib['status'] = SUCCESS_RESULT_STATUS
                rob = etree.SubElement(xml, RIM+"RegistryObjectList")
                for doc in coll.find(monqry, monSel):
                        uid = doc['entryUUID']
                        print 'Found ', uid
                        if refsOnly:
                                r = etree.SubElement(rob, RIM+"ObjectRef", 
                                                     attrib={'home':'',
                                                             'id': uid})
                        else:
                                if searchSubmissions:
                                        xml_submission(rob, doc)
                                else:
                                        xml_document(rob, doc)
                con.disconnect()
                soap = build_soap_msg(resAct, wmesgid, xml)
                web.header('Content-Type', 'application/soap+xml')
                return etree.tostring(soap, pretty_print=True, 
                                      encoding='UTF-8',
                                      #encoding='ISO-8859-1',
                                      xml_declaration=True)
        return "satisfied?"

class XDS_Handler:
    def GET(self):
        return 'Hello, world!'
    def POST(self):
        #print "TE: "+web.ctx.env.get('HTTP_TRANSFER_ENCODING', 'none')
        ct = web.ctx.env.get('CONTENT_TYPE')
        print "GOT Content-type:",ct
        d = parse_content_type(ct)
        data = web.data()
        if d['content_type']=='multipart/related':
           with open('mtom.dat', 'wb') as fp:
                fp.write(data)
           fp = email.parser.FeedParser()
           fp.feed("Content-type: "+ct+"\r\n")
           fp.feed(data)
           msg = fp.close()
           for chunk in handle_mtom_oper(msg):
                yield chunk
        else:
                print "GOT SOAP:\n", data
                yield handle_simple_soap_oper(data)

urls = ("/xdsref/.*", "test",
        "/.*", "XDS_Handler")
app = web.application(urls, globals())

class test:
        def GET(self):
                u = web.ctx.env.get('PATH_INFO')
                raise web.redirect('/static'+u[u.rfind('/'):])

if __name__ == "__main__":
    app.run()
