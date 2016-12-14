"""
The Additional Hydrology toolbox provides a collection of geoprocessing tools
for performing hydrology tasks.

The toolbox is conveniently organized into toolsets which define
 the general feature classes that the tools are applied against.

Mark.Bryant@aecom.com
"""
import sys
import os

# Tools are located in a subfolder called Scripts. Append to path
SCRIPTPATH = os.path.join(os.path.dirname(__file__), "Scripts")
sys.path.append(SCRIPTPATH)

# Do not compile .pyc files for the tool modules.
sys.dont_write_bytecode = True

# Import the tools
from trace_downstream import TraceDownstream

del SCRIPTPATH

class Toolbox(object):
    """ArcGIS Python Toolbox - Additional Hydrology Tools"""
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = 'Additional Hydrology Tools'
        self.alias = 'ahydro'

        # List of tool classes associated with this toolbox
        self.tools = [TraceDownstream]
