"""
trace_downstream.py

Trace Downstream determines the path water will take from a particular location
 to its furthest downhill path. The watershed outlet is often the ocean.

An alternative to using the ready to use services available on
ArcGIS hydrology server http://hydro.arcgis.com/arcgis
as it allow the user to specify a custom flow direction raster

This tool has the additional ability to output the trace as a 3d line,
if also supplied the surface raster.

TODO: 
1) Tool currently required to run as a background process, 
this is to avoid running out of memory when loading large rasters
Look at processing RasterToNumPyArray in blocks to avoid 64bit requirement

2) Look at the optomization options discussed here:
http://stackoverflow.com/questions/17115193/iterating-through-a-numpy-array-and-then-indexing-a-value-in-another-array


Mark.Bryant@aecom.com
20161213
"""
import os
import platform
import numpy
import arcpy


def trace():
    """ Trace finds the line, the filename and error message
    and returns it to the user.
    """
    import inspect
    import traceback
    import sys
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    # script name + line number
    line = tbinfo.split(", ")[1]
    filename = inspect.getfile(inspect.currentframe())
    # Get Python syntax error
    #
    synerror = traceback.format_exc().splitlines()[-1]
    return line, filename, synerror


def move_to_next_pixel(fdr, row, col):
    """ Given fdr (flow direction array), row (current row index), col (current col index).
     return the next downstream neighbor as row, col pair

    See How Flow Direction works
    http://desktop.arcgis.com/en/arcmap/latest/tools/spatial-analyst-toolbox/how-flow-direction-works.htm

    D8 flow direction grid

    | 32 |  64  | 128 |
    | 16 |  X   |  1  |
    |  8 |  4   |  2  |

    """
    # get the fdr pixel value (x,y)
    value = fdr[row, col]

    # Update the row, col based on the flow direction
    if value == 1:
        col += 1
    elif value == 2:
        col += 1
        row += 1
    elif value == 4:
        row += 1
    elif value == 8:
        row += 1
        col -= 1
    elif value == 16:
        col -= 1
    elif value == 32:
        row -= 1
        col -= 1
    elif value == 64:
        row -= 1
    elif value == 128:
        row -= 1
        col += 1
    else:
        # Indetermine flow direction, sink. Do not move.
        row = row
        col = col
    return (row, col)


def get_coord_x(col, cell_width, upper_left):
    """Get the X coordinate in map units, given the
    numpy raster column number,
    pixel size (cell_width),
    point with the coordinate of the lower left corner
    """
    point_x = upper_left.X + ((col-1) * cell_width)  + (cell_width/2.0)
    return point_x


def get_coord_y(row, cell_height, upper_left):
    """Get the Y coordinate in map units, given the
    numpy raster row number,
    pixel size (cell_height),
    point with the coordinate of the lower left corner
    """
    point_y = upper_left.Y - ((row - 1) * cell_height) - (cell_height/2.0)
    return point_y


def get_has_z(surface_raster):
    """Return Environment setting or has_z based on surface_raster availability"""
    environment_value = getattr(arcpy.env, "outputZFlag").upper()
    if environment_value in ['ENABLED', 'DISABLED']:
        return environment_value
    else:
        if surface_raster != None:
            return "ENABLED"
        else:
            return "DISABLED"


def get_template_information(in_features):
    """From the in_features return spatial reference"""
    desc = arcpy.Describe(in_features)
    spatial_ref = desc.spatialReference
    return spatial_ref


def trace_downstream_main(in_features, in_fdr_raster, out_feature_class, surface_raster=None):
    """ Trace downstream from input features, using the flow direction raster
    returning polyline of the trace.
    """
    try:
        arcpy.env.overwriteOutput = True

        # Get information about flow raster.
        # Assuming the surface raster matches in all respects
        fdr_raster = arcpy.Raster(in_fdr_raster)
        cell_width = fdr_raster.meanCellWidth
        cell_height = fdr_raster.meanCellHeight
        max_row = fdr_raster.height  # number of rows
        max_col = fdr_raster.width # number of columns
        upper_left = fdr_raster.extent.upperLeft

        # Create output feature class
        spatial_ref = get_template_information(in_fdr_raster)
        has_z = get_has_z(surface_raster)
        path, name = os.path.split(out_feature_class)
        arcpy.management.CreateFeatureclass(
            path, name, geometry_type="POLYLINE",
            has_z=has_z,
            spatial_reference=spatial_ref)
        # Add a field to transfer FID from input
        arcpy.management.AddField(out_feature_class, "ORIG_FID", "LONG")

        # convert rasters to arrays
        fdr = arcpy.RasterToNumPyArray(in_fdr_raster, nodata_to_value=0)

        # the surface  could be DEM or filled DEM
        if surface_raster != None:
            fill = arcpy.RasterToNumPyArray(surface_raster, nodata_to_value=0)
        ##else:
        ##    fill = numpy.zeros((max_row, max_col), numpy.int)

        # get the max size of the numpy array
        #max_row, max_col = numpy.shape(fdr)

        with arcpy.da.InsertCursor(out_feature_class, ["SHAPE@", "ORIG_FID"]) as insert_cursor:
            with arcpy.da.SearchCursor(in_features, ["SHAPE@XY", "OID@"]) as read_cursor:
                for read_row in read_cursor:
                    pnt = read_row[0]
                    oid = read_row[1]

                    # convert point coordinates into raster indices
                    col = abs(int((upper_left.X - pnt[0]) / cell_width))
                    row = abs(int((upper_left.Y - pnt[1]) / cell_height))

                    # Create an array object needed to create features
                    array = arcpy.Array()

                    if surface_raster != None:
                        # get the Z value of the surface at (row ,col)
                        point_z = numpy.asscalar(fill[row, col])
                    else:
                        point_z = 0

                    # Add the initial point to the array
                    array.add(arcpy.Point(pnt[0], pnt[1], point_z))

                    # Loop thru the trace
                    done = False
                    while not done:
                        # move to downstream cell
                        last_r = row      # store current r value
                        last_c = col      # store current c value
                        row, col = move_to_next_pixel(fdr, row, col)

                        if surface_raster != None:
                            # get the Z value of the surface at (row ,col)
                            point_z = numpy.asscalar(fill[row, col])
                        else:
                            point_z = 0

                        # Calculate the coordinates of x and y (in map units)
                        point_x = get_coord_x(col, cell_width, upper_left)
                        point_y = get_coord_y(row, cell_height, upper_left)

                        # save this coordinate to our list
                        array.add(arcpy.Point(point_x, point_y, point_z))

                        # Check to see if done
                        # If not moved from last location (sink)
                        if last_r == row and last_c == col:
                            done = True
                        # Check to see if out of bounds
                        if row < 0 or row > max_row:
                            done = True
                        if col < 0 or col > max_col:
                            done = True

                    # Done Tracing
                    # add the feature using the insert cursor
                    polyline = arcpy.Polyline(array, spatial_ref, True, False)
                    insert_cursor.insertRow([polyline, oid])

    except arcpy.ExecuteError:
        line, filename, err = trace()
        err_message = 'Geoprocessing error on {} of {}'.format(line, filename)
        print err_message
        arcpy.AddError(err_message)
        arcpy.AddError(arcpy.GetMessages(2))
    except:
        line, filename, err = trace()
        err_message = 'Python error on {} of {} : with error - {}'.format(line, filename, err)
        print err_message
        arcpy.AddError(err_message)
    finally:
        # Final cleanup goes here
        pass


class TraceDownstream(object):
    """Python toolbox tool definition"""
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Trace Downstream"
        self.description = ('Determine the downstream flowpath, '
                            'from the starting point on the supplied surface '
                            'and flow direction raster.')
        self.category = 'Hydrology'
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        in_features = arcpy.Parameter(
            displayName='Input Point Features',
            name='in_features',
            datatype='GPFeatureRecordSetLayer',
            parameterType='Required',
            direction='Input')
        in_features.value = os.path.join(os.path.dirname(__file__), "pointtemplate.lyr")

        in_flow_direction_raster = arcpy.Parameter(
            displayName='Input Flow Direction raster',
            name='in_flow_direction_raster',
            datatype=['DERasterDataset', 'GPRasterLayer'],
            parameterType='Required',
            direction='Input')

        out_feature_class = arcpy.Parameter(
            displayName='Output Trace Feature Class',
            name='out_feature_class',
            datatype='DEFeatureClass',
            parameterType='Required',
            direction='Output')

        surface_raster = arcpy.Parameter(
            displayName='Input surface raster',
            name='in_surface_raster',
            datatype=['DERasterDataset', 'GPRasterLayer'],
            parameterType='Optional',
            direction='Input')

        params = [in_features, in_flow_direction_raster, out_feature_class, surface_raster]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        in_features = parameters[0].value
        in_fdr_raster = parameters[1].valueAsText
        out_feature_class = parameters[2].valueAsText
        surface_raster = parameters[3].valueAsText

        if platform.architecture()[0] != '64bit':
            arcpy.AddError('Must be run in a 64-bit Python environment.')
            return

        feature_count = int(arcpy.management.GetCount(in_features).getOutput(0))
        if feature_count == 0:
            arcpy.AddIDMessage("ERROR", 90148)
            raise arcpy.ExecuteError
        else:
            trace_downstream_main(in_features, in_fdr_raster, out_feature_class, surface_raster)
        return
