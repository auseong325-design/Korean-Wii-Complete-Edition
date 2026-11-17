import unittest
from xml.etree.ElementTree import fromstring
from kwce.wiiroom_feed import xml_response

class RoomXMLTests(unittest.TestCase):
    def test_reference_key_repetition_is_one_container_and_has_no_declaration(self):
        payload=xml_response('Event',dict(adinfo=(dict(pref=2,adid=1),dict(pref=1,adid=1))))
        self.assertTrue(payload.startswith(b'<Event><ver>399</ver>'))
        root=fromstring(payload);self.assertEqual(len(root.findall('adinfo')),1)
        self.assertEqual([(n.tag,n.text)for n in root.find('adinfo')],[('pref','2'),('adid','1'),('pref','1'),('adid','1')])

    def test_empty_container_and_repeated_elements_survive(self):
        root=fromstring(xml_response('Example',dict(posterinfo=[],pageinfo=[dict(name='로컬 & 예시'),dict(name='둘째')],valid=False)))
        self.assertIsNotNone(root.find('posterinfo'));self.assertEqual([p.findtext('name')for p in root.findall('pageinfo')],['로컬 & 예시','둘째']);self.assertEqual(root.findtext('valid'),'0')
