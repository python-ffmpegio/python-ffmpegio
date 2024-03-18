# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath("../src/ffmpegio"))
import ffmpegio

# -- Project information -----------------------------------------------------

project = "python-ffmpegio"
copyright = (
    "2021-2022, Takeshi (Kesh) Ikuma, Louisiana State University Health Sciences Center"
)
author = "Takeshi (Kesh) Ikuma"
release = ffmpegio.__version__

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
    "sphinx.ext.todo",
    "sphinxcontrib.blockdiag",
    "sphinxcontrib.repl",
    "matplotlib.sphinxext.plot_directive",
]
# Looks for objects in external projects

autodoc_typehints = 'description'
# autodoc_type_aliases = {'AgentAssignment': 'AgentAssignment'}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# html_sidebars = {
#     "**": ["globaltoc.html", "relations.html", "sourcelink.html", "searchbox.html"]
# }

# Fontpath for blockdiag (truetype font)
blockdiag_fontpath = "_static/ipagp.ttf"
blockdiag_html_image_format = "SVG"

intersphinx_mapping = {
    "numpy": ("https://numpy.org/doc/stable", None),
}

plot_html_show_source_link = False
plot_html_show_formats = False
plot_pre_code = (
    "import numpy as np\nfrom matplotlib import pyplot as plt\nimport ffmpegio"
)

plot_formats = [("png", 96)]


def setup(app):
    app.add_css_file("css/custom.css")


rst_prolog = """
.. role:: python(code)
    :language: python
    :class: highlight
"""

todo_include_todos = True
