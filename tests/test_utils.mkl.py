from ffmpegio.utils import mkl


if __name__ == "__main__":
    tree = mkl.read_schema()
    root = tree.getroot()
    for child in root:
        print(child.tag, child.attrib)
