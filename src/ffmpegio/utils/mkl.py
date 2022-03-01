from os import path
import xml.etree.ElementTree as ET


def read_schema():
    return ET.parse(path.join(path.dirname(__file__), "ebml_matroska.xml"))
