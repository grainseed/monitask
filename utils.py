from qgis.PyQt.QtCore import Qt,QVariant,QRectF
from qgis.core import (QgsProject, QgsVectorLayer, QgsFields,QgsField,QgsVectorFileWriter,QgsWkbTypes,
                       QgsSymbol,QgsSimpleFillSymbolLayer,QgsSimpleLineSymbolLayer,QgsSingleSymbolRenderer,
                       QgsGeometry,QgsFeatureRequest,QgsPoint,
                       )
from qgis.PyQt.QtGui import (QImage,QPixmap,QPainterPath,QColor,QPen,)
from qgis.gui import QgsMapCanvasItem
import os
import numpy as np
import cv2
from osgeo import gdal,osr
import tempfile
import logging

class FocusCanvasItem(QgsMapCanvasItem):
    def __init__(self, canvas,center):
        super().__init__(canvas)
        self.center = self.toCanvasCoordinates(center)
        self.size = 100

    def setCenter(self, center):
        self.center = self.toCanvasCoordinates(center)

    def center(self):
        return self.center

    def setSize(self, size):
        self.size = size

    def size(self):
        return self.size

    def paint(self, painter, option, widget):
        # path = QPainterPath()
        # path.moveTo(self.center.x(), self.center.y());
        # path.arcTo(self.boundingRect(), 0.0, 360.0)
        # painter.fillPath(path, QColor("green"))
        pen=QPen()
        pen.setStyle(Qt.DashLine)
        pen.setWidth(4)
        pen.setBrush(Qt.yellow)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        r=100
        painter.drawEllipse(self.center,r,r)
        painter.drawLine(self.center.x()-r, self.center.y(), self.center.x()+r, self.center.y())
        painter.drawLine(self.center.x(), self.center.y()-r, self.center.x(), self.center.y()+r)
        #painter.drawRect(self.center.x()-r, self.center.y()-r, r*2, r*2)

def print_log(*args):
    logger = logging.getLogger("Monitask")
    logger.info(",".join([str(msg) for msg in args]))

def create_raster(output_path, columns, rows, nband=1, gdal_data_type=gdal.GDT_Byte, driver='GTiff'):
    ''' returns gdal data source raster object
    '''
    driver = gdal.GetDriverByName(driver)
    output_raster = driver.Create(output_path, int(columns),int(rows), nband, eType=gdal_data_type)
    return output_raster

def numpy_array_to_raster(numpy_array, upper_left_tuple, cell_resolution, nband=1,
                          no_data=0, gdal_data_type=gdal.GDT_Byte, srs_wkid=4326,
                          driver='GTiff'):
    ''' returns a gdal raster data source using a numpy array as datasource
    keyword arguments:
    numpy_array -- numpy array containing data to write to raster
    upper_left_tuple -- the upper left point of the numpy array (should be a tuple structured as (x, y))
    cell_resolution -- the cell resolution of the output raster
    nband -- the band to write to in the output raster
    no_data -- value in numpy array that should be treated as no data
    gdal_data_type -- gdal data type of raster (see gdal documentation for list of values)
    spatial_reference_system_wkid -- well known id (wkid) of the spatial reference of the data
    driver -- string value of the gdal driver to use
    return output_path -- full path to the raster to be written to disk
    '''
    handle, output_path =tempfile.mkstemp(suffix='.tif', prefix=None, dir=None, text=False)
    rows, columns = numpy_array.shape
    # print_log('UL:({}, {})'.format(upper_left_tuple[0], upper_left_tuple[1]))
    # print_log('ROWS: {},COLUMNS:{}'.format(rows, columns))
    # create output raster
    output_raster = create_raster(output_path, int(columns),int(rows),nband,gdal_data_type,driver)
    geotransform = (upper_left_tuple[0], cell_resolution, 0, upper_left_tuple[1], 0, -1*cell_resolution)
    #print_log(geotransform)
    output_raster.SetGeoTransform(geotransform)
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromEPSG(srs_wkid)
    output_raster.SetProjection(spatial_reference.ExportToWkt())
    output_band = output_raster.GetRasterBand(1)
    output_band.SetNoDataValue(no_data)
    output_band.WriteArray(numpy_array)
    output_band.FlushCache()
    output_band.ComputeStatistics(False)
    if os.path.exists(output_path) == False:
        raise Exception('Failed to create raster: %s' % output_path)

    return output_path

def getLayerByTile(title):
    for layer in QgsProject.instance().mapLayers().values():
        if layer.name() == title:
            return layer
    return None

def newOutLayer(settingObj,newLayerName=None,baseimgCRS=None):
    dataTypes = {"String": QVariant.String,
                 "Int": QVariant.Int,
                 "Integer": QVariant.Int,
                 "Double": QVariant.Double,
                 "Date":QVariant.String,
                "DateTime":QVariant.String,
                "Boolean":QVariant.Int}
    fileExtents = {"GeoPackage": ".gpkg",
                   "ShapeFile": ".shp"}

    workDir =settingObj.User_workingdir
    if newLayerName is None or newLayerName.strip()=='':
        layername  = settingObj.General_outlayerName
    else:
        layername=newLayerName

    outFileName= settingObj.General_outFileName
    outFormat  = settingObj.General_outFileFormat
    outFields =eval(str(settingObj.General_outLayerFields))

    outFilepath =os.path.join(workDir ,outFileName +fileExtents[outFormat])
    qgsFields =QgsFields()
    for field in outFields:
        qgsFields.append(QgsField(field[0], dataTypes[field[1]]))

    if baseimgCRS:
        crs=baseimgCRS
    else:
        crs = QgsProject.instance().crs()
    transform_context = QgsProject.instance().transformContext()
    save_options = QgsVectorFileWriter.SaveVectorOptions()
    save_options.layerName =layername
    # If geopackage exists, append layer to it, else create it
    if os.path.exists(outFilepath):
        save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    if outFormat=="ShapeFile":
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "UTF-8"

    writer = QgsVectorFileWriter.create(
        outFilepath,
        qgsFields,
        QgsWkbTypes.Polygon,
        crs,
        transform_context,
        save_options
    )
    if writer.hasError() != QgsVectorFileWriter.NoError:
        print_log(writer.errorMessage())
        del writer
        return None
    else:
        del writer
        rlayer = QgsVectorLayer(outFilepath +"|layername=" +layername, layername, "ogr")
        if not rlayer:
            return None
        else:
            return rlayer

def isOutputLayerValid(output_layer,settingsObj):
    '''
    根据设置中对输出图层的结构定义，判断目标图层是否符合要求
    '''
    isOk = 0
    # 如果未设置字段要求，提示设置，并显示设置窗口，将焦点切换到设置部分
    field_settings = settingsObj.General_outLayerFields
    if field_settings.strip():
        field_settings = eval(field_settings)
        for field in output_layer.fields():
            # QMessageBox.about(None, 'about', str(field.typeName()))
            for required_filed in field_settings:
                if required_filed[5] == "Labeling" and field.name() == required_filed[0] and field.typeName() == \
                        required_filed[1]:
                    isOk += 1

    return isOk>0

def getFieldSources(output_layer,settingsObj):
    results=[]
    field_settings = settingsObj.General_outLayerFields
    if field_settings.strip():
        field_settings = eval(field_settings)
        for required_filed in field_settings:
            if required_filed[3]!="" and required_filed[4]!="":
                for field in output_layer.fields():
                    if field.name() == required_filed[0]:
                        results.append((required_filed[0],required_filed[3],required_filed[4]))
    return results

def newDetectedChangesLayer(settingObj,newLayerName=None,baseimgCRS=None):
    fileExtents = {"GeoPackage": ".gpkg",
                   "ShapeFile": ".shp"}

    workDir =settingObj.User_workingdir
    if newLayerName is None or newLayerName.strip()=='':
        layername  = settingObj.General_changeDetectedlayerName
    else:
        layername=newLayerName
    if layername is None or layername.strip()=='':
        layername="cd_results"

    outFileName= settingObj.General_outFileName
    outFormat  = settingObj.General_outFileFormat
    outFilepath =os.path.join(workDir ,outFileName +fileExtents[outFormat])
    qgsFields =QgsFields()
    qgsFields.append(QgsField("cell_level", QVariant.Int))
    qgsFields.append(QgsField("cell_row", QVariant.Int))
    qgsFields.append(QgsField("cell_col", QVariant.Int))
    qgsFields.append(QgsField("change_tag", QVariant.Int))
    qgsFields.append(QgsField("csim", QVariant.Double))
    qgsFields.append(QgsField("gsim", QVariant.Double))
    qgsFields.append(QgsField("cmutinfo", QVariant.Double,"double",0,2))
    qgsFields.append(QgsField("gmutinfo", QVariant.Double,"double",0,2))
    qgsFields.append(QgsField("chissim", QVariant.Double))
    qgsFields.append(QgsField("ghissim", QVariant.Double))
    qgsFields.append(QgsField("working_img", QVariant.String))
    qgsFields.append(QgsField("prev_img", QVariant.String))
    qgsFields.append(QgsField("working_resolution", QVariant.Double))
    if baseimgCRS:
        crs=baseimgCRS
    else:
        crs = QgsProject.instance().crs()
    transform_context = QgsProject.instance().transformContext()
    save_options = QgsVectorFileWriter.SaveVectorOptions()
    save_options.layerName =layername
    # If geopackage exists, append layer to it, else create it
    if os.path.exists(outFilepath):
        save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    else:
        save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    if outFormat=="ShapeFile":
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "UTF-8"

    writer = QgsVectorFileWriter.create(
        outFilepath,
        qgsFields,
        QgsWkbTypes.Polygon,
        crs,
        transform_context,
        save_options
    )
    if writer.hasError() != QgsVectorFileWriter.NoError:
        print_log(writer.errorMessage())
        del writer
        return None
    else:
        del writer
        rlayer = QgsVectorLayer(outFilepath +"|layername=" +layername, layername, "ogr")
        if not rlayer:
            return None
        else:
            return rlayer

def setParcelDefaultSymbol(targetLayer):
    # create from a defaultsymbol:
    symbol = QgsSymbol.defaultSymbol(targetLayer.geometryType())
    # Create all style layers
    symL1 = QgsSimpleFillSymbolLayer.create({
        "outline_color": "170,0,0,255",
        "outline_width": "0.4",
        "style": "no"
    })
    symL2 = QgsSimpleLineSymbolLayer .create({
          "dash_pattern_offset":"0.8",
          "draw_inside_polygon":"1",
          "line_color":"243,227,9,255",
          "line_style":"dot",
          "line_width":"0.26",
          "offset":"1.2"
    })
    # Add them
    symbol.changeSymbolLayer(0,symL1)
    symbol.appendSymbolLayer(symL2)
    # Create a renderer with the symbol as first parameter
    renderer = QgsSingleSymbolRenderer(symbol)
    # Define the renderer
    targetLayer.setRenderer(renderer)

def get_neigbor_features(this_geom,targetLayer,distance):
    '''
    return the geometries which boundingbox intersect this geometry's
    '''
    obbox ,area, angle,width,height= this_geom.orientedMinimumBoundingBox()
    request = QgsFeatureRequest()
    request.setDistanceWithin(obbox,distance)
    return [f for f in targetLayer.getFeatures(request)]
    #如果需要精确判断相邻图斑，在上面的基础上再通过与this_geom做disjoint判断

def aligned_to_neighbors(this_geom,neighbor_features,torlerance,pixel_resolution):
    '''
    align the edge of the geometry to the neibors with in distance of torlerance in the targetLayer
    '''
    result = this_geom
    if len(neighbor_features)>0:
        neib_geoms=[f.geometry() for f in neighbor_features]
        neib_geom=QgsGeometry.collectGeometry(neib_geoms)
        all_buff=this_geom.buffer(torlerance,5).combine(neib_geom.buffer(torlerance,5)).buffer(-1.5*torlerance,5)
        gap=all_buff.difference(neib_geom).difference(this_geom)
        obbox, area, angle, width, height = gap.orientedMinimumBoundingBox()
        #print_log("width,area,angle of orientedMinimumBoundingBox for gap and gap.area():",width,area,angle,gap.area())
        if gap.area()>pixel_resolution*pixel_resolution:
            temp_result=this_geom.combine(gap)
            if temp_result.isMultipart():
                #print_log(" The aligned result is multipart, keep the max only ")
                parts_details = []
                # 保留主要的：最大的，其他保留面积超过最小图斑指标，且非细条、面积占比超过10%的图斑
                max_area = 0
                for part in temp_result.asGeometryCollection():
                    part_details = {}
                    part_details["area"] = part.area()
                    if part_details["area"] <= 0: continue
                    if part_details["area"] > max_area:
                        max_area = part_details["area"]
                    part_details["part"] = part
                    parts_details.append(part_details)
                for part_detail in parts_details:
                    if part_detail["area"] == max_area:
                       result=part_detail["part"]
            else:
                result=temp_result
            #result=result.simplify(1*pixel_resolution)
    return result

def cosine_similarity(vector_a, vector_b):
    """
    计算两个向量之间的余弦相似度
    :param vector_a: 向量 a
    :param vector_b: 向量 b
    :return: sim
    """
    try:
        #vector_a = np.mat(vector_a)
        #vector_b = np.mat(vector_b)
        #print_log(vector_a,vector_b)
        #print((vector_a @ vector_b).shape)
        num = float(vector_a @ vector_b)
        #num = float(vector_a * vector_b.T)
        denom = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
        sim = int(num / denom *100)
    except:
        sim=0
    finally:
        return sim

def correlation_coefficient(vector_a, vector_b):
    '''
    计算两个向量之间的相关系数，取值范围为[-1,1]，相关系数的绝对值越大，相关性越强；相关系数越接近于0，相关度越弱。
    '''
    vector_a = np.mat(vector_a)
    vector_b = np.mat(vector_b)
    return int(np.corrcoef(vector_a, vector_b)[0, 1]*100)

def get_entropy(image, base=2):
    '''
    计算图像的信息熵，以用于评估图像的复杂程度
    :param image:
    :param base:
    :return:
    '''
    bandcount=1 if image.ndim==2 else image.shape[2]
    if bandcount>1:
        image = image[:, :, ::-1].transpose((2, 0, 1))
    else:
        image = image[np.newaxis,:]
    bands_entropy=[]
    for i in range(bandcount):
        base = math.e if base is None else base
        band=image[i].reshape(-1)
        size = band.shape[-1]
        px = np.histogram(image[i], 255, (1, 255))[0] / (size*1.0)
        hx =-np.sum(px * np.log(px + 1e-8) / np.log(base))
        bands_entropy.append(hx)
        # values, counts = np.unique(image[i].reshape(-1), return_counts=True)
        # norm_counts = counts *1.0 / counts.sum()
        # base = math.e if base is None else base
        # bands_entropy.append(-(norm_counts * np.log(norm_counts + 1e-8) / np.log(base)).sum())
    return int(sum(bands_entropy)/bandcount/8*100) #转换为百分比

def mutual_info(image1,image2,base=2):
    '''
    计算image1和image2之间的互信息，反映两者之间相互依赖程度的度量
    image1和image2的维度数必须一致
    '''
    bandcount=1 if image1.ndim==2 else image1.shape[2]
    if image1.shape!=image2.shape:# "求两幅影像的互信息，两者的大小必须一致"
        if bandcount>1:
            h1,w1,_=image1.shape
            h2,w2,_=image2.shape
        else:
            h1,w1=image1.shape
            h2,w2=image2.shape
        hm=min(h1,h2)
        wm=min(w1,w2)
        image1=cv2.resize(image1,(wm,hm))
        image2=cv2.resize(image2,(wm,hm))

    if bandcount>1:
        image1 = image1[:, :, ::-1].transpose((2, 0, 1))
        image2 = image2[:, :, ::-1].transpose((2, 0, 1))
    else:
        image1 = image1[np.newaxis,:]
        image2 = image2[np.newaxis,:]
    bands_mutual_info=[]
    for i in range(bandcount):
        size = image1[i].reshape(-1).shape[-1]
        entropy1=get_entropy(image1[i], base=base)
        entropy2=get_entropy(image2[i], base=base)
        #print_log(image1[i].shape,image2[i].shape)
        entropy_1_2 = np.histogram2d(image1[i].reshape(-1), image2[i].reshape(-1), [255,255], [[1, 255], [1, 255]])[0]/(1.0 * size)
        #entropy_1_2 = np.histogram2d(image1[i], image2[i])[0]/(1.0 * size)
        entropy_1_2 = np.sum(-entropy_1_2 * np.log(entropy_1_2 + 1e-8)/ np.log(base))
        entropy_1_2 = entropy_1_2/8*100  # 转换为百分比
        #print_log("Entropies:",entropy1,entropy2,entropy_1_2,entropy1+entropy2-entropy_1_2)
        MI=entropy1+entropy2-entropy_1_2
        normMI=2*MI/(entropy1+entropy2)*100 #取值范围归一化处理到0-100
        bands_mutual_info.append(normMI)
    return sum(bands_mutual_info) / bandcount

def rgb_histogram(image):
    '''
    生成每个波段由128个值，三个波段共384个值表示的直方图矢量
    '''
    band_count=1 if image.ndim==2 else image.shape[2]
    if band_count>1:
        image = image[:, :, ::-1].transpose((2, 0, 1))
    else:
        image = image[np.newaxis,:]
    hist=[]
    for i in range(band_count):
        band = image[i].reshape(-1)
        size = band.shape[-1]
        hist.append(np.histogram(image[i], 128, (1, 255))[0] / (size*1.0))
    result=np.array(hist).reshape(-1).astype(np.single)
    #print_log("Histgram:",result.shape,result.dtype)
    return result

def cv2QImage(cvimage):
    # 8-bits unsigned, NO. OF CHANNELS=1
    if cvimage.dtype == np.uint8:
        channels = 1 if len(cvimage.shape) == 2 else cvimage.shape[2]
    if channels == 3: # CV_8UC3
        # Copy input Mat
        # Create QImage with same dimensions as input Mat
        cvimg = cv2.cvtColor(cvimage, cv2.COLOR_BGR2RGB)
        img = QImage(cvimg.data, cvimg.shape[1], cvimg.shape[0], cvimg.strides[0], QImage.Format_RGB888)
        return img
    elif channels == 1:
        # Copy input Mat
        # Create QImage with same dimensions as input Mat
        img = QImage(cvimage.data, cvimage.shape[1], cvimage.shape[0], cvimage.strides[0], QImage.Format_Indexed8)
        return img
    else:
        return QImage()
def clipBGImageByRectangle(qgsRasterLayer,qgsRectangle,width_px,height_px):
  data_provider=qgsRasterLayer.dataProvider()
  if str(qgsRasterLayer.rasterType())=="RasterLayerType.SingleBandColorData":
      block=data_provider.block(1,
          qgsRectangle,
          width_px,
          height_px)
      data = np.array(block.data()).astype(np.uint8)
      data = data.reshape(block.height(), block.width(), 4)
      data = data[:, :, 0:3]
  elif str(qgsRasterLayer.rasterType())=="RasterLayerType.MultiBand":
      bands_data=[]
      for i in range(1,4):
          block=data_provider.block(i,qgsRectangle,width_px,height_px)
          bands_data.append(np.array(block.data()).astype(np.uint8).reshape(block.height(), block.width()))
      data=np.stack(bands_data)
      data=np.transpose(data, (1, 2, 0))

  return data

def change_detect(encoder, image1, image2):
    eb1 = encoder.get_embedding(image1)
    eb2 = encoder.get_embedding(image2)
    sim = cosine_similarity(eb1, eb2)
    mutinfo = 0#mutual_info(image1, image2)
    hissim = cosine_similarity(rgb_histogram(image1), rgb_histogram(image2))
    return sim, mutinfo, hissim

def transfer_image_style(image, ref_img):
    out = np.zeros_like(image)
    ch = 1 if image.ndim == 2 else image.shape[2]
    if ch>1:
        for i in range(ch):
            hist_img, _ = np.histogram(image[:, :, i], 256)
            hist_ref, _ = np.histogram(ref_img[:, :, i], 256)
            cdf_img = np.cumsum(hist_img)
            cdf_ref = np.cumsum(hist_ref)

            for j in range(256):
                tmp = abs(cdf_img[j] - cdf_ref)
                tmp = tmp.tolist()
                #print(min(tmp))
                idx = tmp.index(min(tmp))  # 找出tmp中最小的数，得到这个数的索引
                out[:, :, i][ref_img[:, :, i] == j] = idx
    else:
        hist_img = cv2.calcHist([image], [0], None, [256], [0, 256])
        hist_ref = cv2.calcHist([ref_img], [0], None, [256], [0, 256])
        # 计算累计直方图
        tmp_ref = 0.0
        h_ref = hist_ref.copy()
        for i in range(256):
            tmp_ref += h_ref[i]
            h_ref[i] = tmp_ref
        tmp = 0.0
        h_acc = hist_img.copy()
        for i in range(256):
            tmp += hist_img[i]
            h_acc[i] = tmp
        # 计算映射
        diff = np.zeros([256, 256])
        for i in range(256):
            for j in range(256):
                diff[i][j] = np.fabs(h_ref[j] - h_acc[i])
        M = np.zeros(256)
        for i in range(256):
            index = 0
            minum = diff[i][0]  # min = 1.
            for j in range(256):
                if (diff[i][j] < minum):
                    minum = diff[i][j]
                    index = int(j)
            M[i] = index
        out = M[image].astype(np.float32)
    return out

# # 图片相似度计算常规方法：https://zhuanlan.zhihu.com/p/68215900
# # 通过得到RGB每个通道的直方图来计算相似度
# def classify_hist_with_split(image1, image2, size=(255, 255)):
#     # 将图像resize后，分离为RGB三个通道，再计算每个通道的相似值
#     image1 = cv2.resize(image1, size)
#     image2 = cv2.resize(image2, size)
#     sub_image1 = cv2.split(image1)
#     sub_image2 = cv2.split(image2)
#     sub_data = 0
#     for im1, im2 in zip(sub_image1, sub_image2):
#         sub_data += calculate(im1, im2)
#     sub_data = sub_data / 3
#     return sub_data
#
# # 计算单通道的直方图的相似值
# def calculate(image1, image2):
#     hist1 = cv2.calcHist([image1], [0], None, [256], [0.0, 255.0])
#     hist2 = cv2.calcHist([image2], [0], None, [256], [0.0, 255.0])
#     # 计算直方图的重合度
#     degree = 0
#     for i in range(len(hist1)):
#         if hist1[i] != hist2[i]:
#             degree = degree + (1 - abs(hist1[i] - hist2[i]) / max(hist1[i], hist2[i]))
#         else:
#             degree = degree + 1
#     degree = degree / len(hist1)
#     return degree
#
# #另一种直方图相似度算法
# def create_rgb_hist(image):
#     '''
#     创建 RGB 三通道直方图（直方图矩阵）
#     '''
#     h, w, c = image.shape
#     # 创建一个（16*16*16,1）的初始矩阵，作为直方图矩阵
#     # 16*16*16的意思为三通道每通道有16个bins
#     rgbhist = np.zeros([16 * 16 * 16, 1], np.float32)
#     bsize = 256 / 16
#     for row in range(h):
#         for col in range(w):
#             b = image[row, col, 0]
#             g = image[row, col, 1]
#             r = image[row, col, 2]
#             # 人为构建直方图矩阵的索引，该索引是通过每一个像素点的三通道值进行构建
#             index = int(b / bsize) * 16 * 16 + int(g / bsize) * 16 + int(r / bsize)
#             # 该处形成的矩阵即为直方图矩阵
#             rgbhist[int(index), 0] += 1
#     return rgbhist
#
# def hist_compare(image1, image2):
#     """直方图比较函数"""
#     # 创建第一幅图的rgb三通道直方图（直方图矩阵）
#     hist1 = create_rgb_hist(image1)
#     # 创建第二幅图的rgb三通道直方图（直方图矩阵）
#     hist2 = create_rgb_hist(image2)
#     # 进行三种方式的直方图比较
#     match1 = cv.compareHist(hist1, hist2, cv.HISTCMP_BHATTACHARYYA)
#     match2 = cv.compareHist(hist1, hist2, cv.HISTCMP_CORREL)
#     match3 = cv.compareHist(hist1, hist2, cv.HISTCMP_CHISQR)
#     print_log("巴氏距离：%s, 相关性：%s, 卡方：%s" %(match1, match2, match3))
