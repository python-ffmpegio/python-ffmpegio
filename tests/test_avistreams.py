from ffmpegio.streams import AviStreams
from ffmpegio import open


def test_open():
    url1 = "tests/assets/testvideo-1m.mp4"
    url2 = "tests/assets/testaudio-1m.mp3"
    with open((url1, url2), "rav", t=1, blocksize=0) as reader:
        for st, data in reader:
            print(st, data['shape'], data['dtype'])

    print('testing "rvv"')
    with open(
        url1,
        "rvv",
        t=1,
        blocksize=0,
        filter_complex="[0:v]split=2[out1][out2]",
        map=["[out1]", "[out2]"],
    ) as reader:
        for st, data in reader:
            print(st, data['shape'], data['dtype'])

    print('testing "raa"')
    with open(
        url2,
        "raa",
        t=1,
        blocksize=0,
        filter_complex="[0:a]asplit=2[out1][out2]",
        map=["[out1]", "[out2]"],
    ) as reader:
        for st, data in reader:
            print(st, data['shape'], data['dtype'])
        # print(reader.readlog())
        
def test_avireadstream():
    url1 = "tests/assets/testvideo-1m.mp4"
    url2 = "tests/assets/testaudio-1m.mp3"
    with AviStreams.AviMediaReader(url1, url2, t=1, blocksize=0) as reader:
        for st, data in reader:
            print(st, data['shape'], data['dtype'])

    with AviStreams.AviMediaReader(url1, url2, t=1, blocksize=1) as reader:
        for data in reader:
            print({k: (v['shape'], v['dtype']) for k, v in data.items()})

    with AviStreams.AviMediaReader(
        url1, url2, t=1, blocksize=1000, ref_stream="a:0"
    ) as reader:
        for data in reader:
            print({k: (v['shape'], v['dtype']) for k, v in data.items()})

    with AviStreams.AviMediaReader(url1, url2, t=1) as reader:
        print(reader.specs())
        print(reader.types())
        print(reader.rates())
        print(reader.dtypes())
        print(reader.shapes())
        print(reader.get_stream_info("v:0"))
        print(reader.get_stream_info("a:0"))

        data = reader.readall()
        print({k: (v['shape'], v['dtype']) for k, v in data.items()})


if __name__ == "__main__":
    url = "tests/assets/testmulti-1m.mp4"
    url1 = "tests/assets/testvideo-1m.mp4"
    url2 = "tests/assets/testaudio-1m.mp3"

    from pprint import pprint

    with AviStreams.AviMediaReader(url1, url2, t=1) as reader:
        reader._reader.wait()
        print(f'thread is running {reader._reader.is_alive()}')
        pprint(reader.specs())
        print(reader.types())
        print(reader.rates())
        print(reader.dtypes())
        print(reader.shapes())
        print(reader.get_stream_info("v:0"))
        print(reader.get_stream_info("a:0"))

        data = reader.readall()
        print({k: (v['shape'], v['dtype']) for k, v in data.items()})
