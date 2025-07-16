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
    "2021-2025, Takeshi (Kesh) Ikuma, Louisiana State University Health Sciences Center"
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
    "sphinx.ext.graphviz",
    "sphinxcontrib.repl",
    "matplotlib.sphinxext.plot_directive",
]
# Looks for objects in external projects


# Autodoc configuration
autodoc_member_order = "groupwise"
autodoc_type_aliases = {
    "ArrayLike": "~numpy.typing.ArrayLike",
    "NDArray": "~numpy.typing.NDArray",
    "ff": "ffmpegio"
}
autodoc_mock_imports = ["builtins"]
autodoc_typehints_format = "short"
# autodoc_class_signature = "separated"
autodoc_default_options = {"exclude-members": "__new__", "class-doc-from": "init"}
autodoc_typehints = "description"

overloads_location = 'signature'

# Intersphinx configuration
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    "python": ("https://docs.python.org/3/", None),
}

autodoc_typehints = 'description'
# autodoc_type_aliases = {'AgentAssignment': 'AgentAssignment'}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

copybutton_selector = "div:not(.output_area) > div.highlight > pre"

graphviz_output_format = 'svg'

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_book_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]


# html_logo = "images/logo.png"
html_theme_options = {
    # "logo": {
    #     "image_light": "images/wave-reflection-model-light.png",
    #     "image_dark": "images/wave-reflection-model-dark.png",
    # },
    "path_to_docs": "docs/",
    "repository_url": "https://github.com/tikuma-lsuhsc/pyLeTalker",
    # "repository_branch": branch_or_commit,
    "use_repository_button": True,
    "use_source_button": True,
    "show_toc_level": 2,
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
