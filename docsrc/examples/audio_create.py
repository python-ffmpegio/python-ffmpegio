import numpy as np
from ffmpegio import audio
from matplotlib import pyplot as plt

fs = 8000
# x = audio.create(
#     "aevalsrc",
#     "sin(420*2*PI*t)|cos(430*2*PI*t)",
#     c="FC|BC",
#     nb_samples=fs,
#     sample_rate=fs,
# )

# x = audio.create(
#     "flite",
#     text="The rainbow is a division of white light into many beautiful colors.",
#     nb_samples=1024 * 8,
# )

# x = audio.create("anoisesrc", d=6, c="pink", r=fs, a=0.5)

x = audio.create("sine", f=220, b=4, d=5, r=fs)

t = np.arange(x.shape[0],dtype=float)*fs
plt.plot(t, x)
plt.show()