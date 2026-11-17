"""XML shape used by the pinned public Room server, without running its modules."""
from xml.etree.ElementTree import Element,SubElement,tostring

def xml_response(name,fields):
    root=Element(name);SubElement(root,'ver').text='399'
    def add(parent,values):
        for key,value in values.items():
            # Public RepeatedKey: one container with repeated child fields.
            if isinstance(value,tuple):
                child=SubElement(parent,key)
                for item in value:add(child,item)
                continue
            # An empty RepeatedElement list retains its empty container.
            if isinstance(value,list)and not value:SubElement(parent,key);continue
            for item in(value if isinstance(value,list)else[value]):
                child=SubElement(parent,key)
                if isinstance(item,dict):add(child,item)
                elif isinstance(item,bool):child.text=str(int(item))
                elif isinstance(item,(str,int)):child.text=str(item)
                elif isinstance(item,bytes):
                    import base64
                    child.text=base64.b64encode(item).decode('ascii')
                elif item is not None:raise ValueError('Unsupported Room XML type')
    add(root,fields)
    return tostring(root,encoding='utf-8',xml_declaration=False)+b'\n'
