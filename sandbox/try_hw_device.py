from ffmpegio import ffmpegprocess as ffprocess

print(ffprocess.versions())

ffprocess.run({"global_options": {"init_hw_device": "cuda"}})
