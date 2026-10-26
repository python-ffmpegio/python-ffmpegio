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

from docutils import nodes
from sphinx.application import Sphinx

sys.path.insert(0, os.path.abspath("../src/ffmpegio"))
import ffmpegio

# -- Project information -----------------------------------------------------

project = "python-ffmpegio"
copyright = (
    "2021-2026, Takeshi (Kesh) Ikuma, Louisiana State University Health Sciences Center"
)
author = "Takeshi (Kesh) Ikuma"
release = ffmpegio.__version__

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    # "sphinx_autodoc_typehints",
    # "sphinx.ext.napoleon",
    # "sphinx_toolbox.more_autodoc.overloads",
    # "sphinx_toolbox.more_autodoc.autonamedtuple",
    # "sphinx_toolbox.more_autodoc.autoprotocol",
    # "sphinx_toolbox.more_autodoc.autotypeddict",
    # "sphinx_toolbox.more_autodoc.genericalias",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
    "sphinx.ext.todo",
    # "sphinx.ext.graphviz",
    # "sphinxcontrib.repl",
    "matplotlib.sphinxext.plot_directive",
]
# Looks for objects in external projects


# Autodoc configuration
autodoc_member_order = "groupwise"
autodoc_type_aliases = {
    "ArrayLike": "~numpy.typing.ArrayLike",
    "NDArray": "~numpy.typing.NDArray",
    "ff": "ffmpegio",
}
autodoc_typehints = "description"
autodoc_type_aliases = {
    "RawDataBlob": "ffmpegio.typing.RawDataBlob",
    "ShapeTuple": "ffmpegio.typing.ShapeTuple",
    "DTypeString": "ffmpegio.typing.DTypeString",
    "MapString": "ffmpegio.typing.MapString",
    "FFmpegOptionDict": "ffmpegio.typing.FFmpegOptionDict",
    "ProgressCallback": "ffmpegio.typing.ProgressCallback",
    "FFmpegInputUrlComposite": "ffmpegio.typing.FFmpegInputUrlComposite",
    "FFmpegInputOptionTuple": "ffmpegio.typing.FFmpegInputOptionTuple",
    "FFmpegOutputUrlComposite": "ffmpegio.typing.FFmpegOutputUrlComposite",
    "FFmpegOutputOptionTuple": "ffmpegio.typing.FFmpegOutputOptionTuple",
    "FilterGraphObject": "ffmpegio.filtergraph.FilterGraphObject",
}
# autodoc_mock_imports = ["builtins"]
# autodoc_typehints_format = "short"
# # autodoc_class_signature = "separated"
# autodoc_default_options = {"exclude-members": "__new__", "class-doc-from": "init"}
# overloads_location = "top"

# Intersphinx configuration
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": (
        "https://numpy.org/doc/stable/",
        "https://numpy.org/doc/stable/objects.inv",
    ),
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    "pillow": ("https://pillow.readthedocs.io/en/stable/", None),
}


# Map your missing types to their raw documentation URLs
MISSING_TYPE_LINKS = {
    "numpy.typing.ArrayLike": "https://numpy.org/doc/stable/reference/typing.html#numpy.typing.ArrayLike",
}


def link_missing_types(app: Sphinx, env, node, contnode):
    # Only target Python domain types/classes/objects
    if node.get("refdomain") == "py":
        target = node.get("reftarget")
        if target in MISSING_TYPE_LINKS:
            # Construct a hardcoded external reference node
            newnode = nodes.reference(
                "", "", internal=False, refuri=MISSING_TYPE_LINKS[target]
            )
            newnode.append(contnode)
            return newnode
    return None


# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

copybutton_selector = "div:not(.output_area) > div.highlight > pre"

graphviz_output_format = "svg"

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
    "repository_url": "https://github.com/ffmpegio/ffmpegio",
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
    app.connect("missing-reference", link_missing_types)
    app.add_css_file("css/custom.css")


rst_prolog = """
.. role:: python(code)
    :language: python
    :class: highlight
"""

todo_include_todos = True
