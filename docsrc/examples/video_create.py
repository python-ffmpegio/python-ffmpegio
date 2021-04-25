from ffmpegio import video
from matplotlib import animation, pyplot as plt

A = video.create("mandelbrot", r=25, size="640x480", duration=10.0)

# First set up the figure, the axis, and the plot element we want to animate
fig = plt.figure()

n = A.shape[0]
im = plt.imshow(A[0, ...])
i = 0

# initialization function: plot the background of each frame
def init():
    im.set_data(A[i, ...])
    return [im]


# animation function.  This is called sequentially
def animate(i):
    im.set_array(A[i, ...])
    return [im]


anim = animation.FuncAnimation(
    fig, animate, frames=A.shape[0], init_func=init, interval=1000 / 25, blit=True
)

plt.show()