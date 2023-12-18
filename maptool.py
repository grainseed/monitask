from qgis.PyQt.QtCore import QTranslator, QCoreApplication, Qt, QObject,QRectF,QVariant
from qgis.PyQt.QtGui import (
    QColor,QPainterPath,QImage,QPixmap,QPen
)
from qgis.gui  import QgsMapTool,QgsMapToolEmitPoint,QgsMapCanvasItem,QgsRubberBand,QgsHighlight,QgsMapToolIdentify,QgsMapToolIdentifyFeature
from qgis.core import (Qgis,QgsProject,QgsWkbTypes,QgsPoint,QgsPointXY,QgsRectangle,QgsRasterLayer,QgsMessageLog,
                       QgsMapLayer,QgsVectorLayer,QgsFields,QgsField,QgsFeature,QgsGeometry,QgsLineSymbol,QgsMarkerSymbol,
                       QgsSimpleFillSymbolLayer,QgsSymbol,QgsSingleSymbolRenderer,
                       QgsHashedLineSymbolLayer,QgsLineSymbol,QgsInvertedPolygonRenderer, QgsSimpleLineSymbolLayer,
                       QgsCategorizedSymbolRenderer,QgsRendererCategory,QgsPalLayerSettings,QgsVectorLayerSimpleLabeling,
                       QgsRasterBlock, QgsProcessing, QgsCoordinateReferenceSystem, QgsRasterBandStats,
                       QgsSingleBandGrayRenderer, QgsContrastEnhancement,QgsCoordinateTransform,QgsTolerance,QgsFeatureRequest,
                        QgsWkbTypes,QgsRasterDataProvider,QgsPalettedRasterRenderer,QgsSymbolLayer,QgsProperty,
                       )
from qgis.PyQt.QtWidgets import QMessageBox,QGraphicsScene,QApplication
import numpy as np
import math,os
from osgeo import gdal, ogr, osr
from qgis.core import QgsRasterBlock, QgsProcessing, QgsCoordinateReferenceSystem, QgsRasterBandStats, \
    QgsSingleBandGrayRenderer, QgsContrastEnhancement
#from qgis import processing
import cv2
#from .settings import SettingsClass
from .labelbase import LabelSample
from .utils import (get_neigbor_features,aligned_to_neighbors,cosine_similarity,get_entropy,
                    rgb_histogram,cv2QImage,clipBGImageByRectangle,numpy_array_to_raster,print_log,
                    mutual_info,)
from .histogram_align import get_new_img,get_infer_map


class LabelCheckTool(QgsMapToolIdentifyFeature):
    def __init__(self, monitask):
        self.monitask = monitask
        self.iface = monitask.iface
        self.canvas = self.iface.mapCanvas()
        self.layer = self.iface.activeLayer()
        self.currentSampleLocation=None
        QgsMapToolIdentifyFeature.__init__(self, self.canvas, self.layer)
        self.iface.currentLayerChanged.connect(self.active_changed)

    def active_changed(self, layer):
        try:
            if self.layer:
                self.layer.removeSelection()
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
                self.layer = layer
                self.setLayer(self.layer)
        except:
            pass

    def canvasPressEvent(self, event):
        found_features = self.identify(event.x(), event.y(), [self.layer], QgsMapToolIdentify.TopDownAll)
        self.layer.selectByIds([f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection)
        id=-1
        rect=None
        for f in found_features:
            rect=f.mFeature.geometry().boundingBox()
            id=f.mFeature.id()
            break
        w=self.monitask.labelCheckWidget.curSampleGraphicsView.geometry().width()
        h=self.monitask.labelCheckWidget.curSampleGraphicsView.geometry().height()
        if rect:
            cv_image=clipBGImageByRectangle(self.monitask.wl.baseimg_layer,rect,w,h)
            scene = QGraphicsScene()
            scene.addPixmap(QPixmap(cv2QImage(cv_image)))
            self.monitask.labelCheckWidget.curSampleGraphicsView.setScene(scene)
            self.monitask.labelCheckWidget.curSampleGraphicsView.show()
            sample=self.monitask.lb.getLabelSampleByLayerAndFeatid(self.layer.name(),id)
            if sample:
                self.monitask.labelCheckWidget.sampidEdit.setText(str(sample.id))
                self.monitask.labelCheckWidget.lblidEdit.setText(str(sample.labelid))
                lblitem=self.monitask.lb.getLabelItemById(sample.labelid)
                if lblitem:
                    self.monitask.labelCheckWidget.labelEdit.setText(lblitem.title)
                self.monitask.labelCheckWidget.currentSampId = sample.id
                self.monitask.labelCheckWidget.currentLabelId = sample.labelid
                self.monitask.labelCheckWidget.currentLayerName = self.layer.name()
                self.currentSampleLocation=QgsPointXY(sample.longitude,sample.latitude)
            else:
                self.monitask.labelCheckWidget.sampidEdit.setText("")
                self.monitask.labelCheckWidget.lblidEdit.setText("")
                self.monitask.labelCheckWidget.labelEdit.setText("(not of this output layer)")


    def deactivate(self):
        self.layer.removeSelection()

    def panBack(self):
        self.canvas.setCenter(self.currentSampleLocation)
        self.canvas.refresh()

class PointTool(QgsMapTool):
    def __init__(self, monitask):
        self.monitask = monitask
        self.iface = monitask.iface
        self.canvas = self.iface.mapCanvas()
        QgsMapTool.__init__(self, self.canvas)

    def canvasPressEvent(self, event):
        pass

    def canvasMoveEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()

        point = self.canvas.getCoordinateTransform().toMapCoordinates(x, y)

    def canvasReleaseEvent(self, event):
        #Get the click
        x = event.pos().x()
        y = event.pos().y()
        point = self.canvas.getCoordinateTransform().toMapCoordinates(x, y)
        layer=self.canvas.currentLayer()
        searchRadius = (QgsTolerance.toleranceInMapUnits(5, layer,
                                                         self.canvas.mapSettings(), QgsTolerance.Pixels))
        rect = QgsRectangle()
        rect.setXMinimum(point.x() - searchRadius)
        rect.setXMaximum(point.x() + searchRadius)
        rect.setYMinimum(point.y() - searchRadius)
        rect.setYMaximum(point.y() + searchRadius)
        layer.select(layer.attributeList(), rect, True, True)
        for feature in layer:
            pass

    def activate(self):
        pass

    def deactivate(self):
        pass

    def isZoomTool(self):
        return False

    def isTransient(self):
        return False

    def isEditTool(self):
        return True


#以下源自：https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/canvas.html#writing-custom-map-tools
class SegMapTool(QgsMapToolEmitPoint):
  def __init__(self, monitask):
    self.monitask=monitask
    self.iface=monitask.iface
    self.canvas = self.iface.mapCanvas()
    QgsMapToolEmitPoint.__init__(self, self.canvas)

    #self.workingExtent=self.canvas.extent()
    self.workingExtent=None
    self.native_resolution=1.0
    self.working_resolution = self.native_resolution
    self.workImgSizePx=1024
    self.working_extent_layer=None
    self.temp_mask_layer=None
    self.segany=None
    self.seg_enabled=False
    #self.seg_params=None
    self.workingImg=None
    self.mask_item=None
    self.latest_inserted_sample_id=-1
    self.click_crs_points=[] #记录点击的原始坐标
    self.click_points=[]
    self.click_points_mode=[]
    self.highlightItems=[]
    self.latest_ids_added=[]
    self.latest_parcel_centroid=None

    self.debug_layer_point=None
    self.debug_layer_line=None
    self.debug_layer_polygon=None
    self.extending_labelid=-1
    self.lastUsed_labelid = -1
    self.CD_InProcessing=False

    self.setCursor(Qt.CrossCursor)
    self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
    self.rubberBand.setFillColor(QColor(0,0,0,0))
    self.rubberBand.setStrokeColor(QColor(250, 250, 0))
    self.rubberBand.setLineStyle(Qt.DotLine)
    self.rubberBand.setWidth(3)
    self.reset()

    #self.canvas.extentsChanged.connect(self.getWorkingExtent)

  def reset(self):
    self.startPoint = self.endPoint = None
    self.isEmittingPoint = False
    self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)

  def clearCanvasItem(self):
      self.canvas.scene().removeItem(self.rubberBand)

  def clearWorkLayers(self):
      try:
          if self.temp_mask_layer:
              QgsProject.instance().removeMapLayer(self.temp_mask_layer.id())
              self.temp_mask_layer=None
          if self.working_extent_layer:
              QgsProject.instance().removeMapLayer(self.working_extent_layer.id())
              self.working_extent_layer=None
          if self.debug_layer_point:
              QgsProject.instance().removeMapLayer(self.debug_layer_point.id())
              self.debug_layer_point=None
          if self.debug_layer_polygon:
              QgsProject.instance().removeMapLayer(self.debug_layer_polygon.id())
              self.debug_layer_polygon=None
          if self.debug_layer_line:
              QgsProject.instance().removeMapLayer(self.debug_layer_line.id())
              self.debug_layer_line=None

      except:
          self.temp_mask_layer = None
          self.working_extent_layer = None

  def canvasPressEvent(self, e):
    self.startPoint = self.toMapCoordinates(e.pos())
    self.endPoint = self.startPoint
    self.isEmittingPoint = True
    self.showRect(self.startPoint, self.endPoint)


  def canvasReleaseEvent(self, e):
    def pushPointInList(point,button_type):
        if button_type == 1:  # left button
            self.click_points.append(point)
            self.click_points_mode.append(1)
        elif button_type == 2:  # right button
            self.click_points.append(point)
            self.click_points_mode.append(0)

    self.isEmittingPoint = False
    r = self.rectangle()
    #print_log("******************************seg_enabled:")
    if r is not None:
        print_log("Rectangle:", r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum())
    elif self.seg_enabled:
        #todo:这里先判断startPoint是否在当前工作区内，如果是继续。否则需提示，并结束，更新工作区后，并以新点击的位置为中心，将底图平移到提示框类，再继续。
        imgcrs_point=self.transCRSFromProj2Img(self.startPoint)
        if  self.workingExtent is None:
            self.setWorkingExtent(imgcrs_point)

        self.click_crs_points.append(imgcrs_point)
        if  self.workingExtent.contains(imgcrs_point):
            pushPointInList(self.toWorkingExtentCoordinates(imgcrs_point), e.button())
            self.do_seg()
        else:
            #print_log("超出当前工作窗口，需切换工作窗口，取消当前窗口未完成的采样，并切换到以点击位置为中心的新工作区")
            self.cancel()
            self.setWorkingExtent(imgcrs_point)
            self.canvas.setCenter(self.startPoint)
            pushPointInList(self.toWorkingExtentCoordinates(imgcrs_point),e.button())
            self.do_seg()

  def transCRSFromProj2Img(self,proj_point):
      '''将点从当前project的坐标系统转为底图影像的坐标系统'''
      proj_crs = QgsProject.instance().crs()
      img_crs = self.monitask.wl.crs
      if proj_crs.authid()!=img_crs.authid():
          transformContext = QgsProject.instance().transformContext()
          xform = QgsCoordinateTransform(proj_crs, img_crs, transformContext)
          img_point=xform.transform(proj_point)
      else:
          img_point=proj_point
      return img_point

  def toWorkingExtentCoordinates(self,mapPoint):
      imgX=math.ceil((mapPoint.x()-self.workingExtent.xMinimum())/self.working_resolution)
      imgY=math.ceil((self.workingExtent.yMaximum()-mapPoint.y())/self.working_resolution)
      return [imgX,imgY]

  def canvasMoveEvent(self, e):
    if not self.isEmittingPoint:
      return
    self.endPoint = self.toMapCoordinates(e.pos())
    #self.showRect(self.startPoint, self.endPoint)

  def showRect(self, startPoint, endPoint):
    self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
    if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
      return

    point1 = QgsPointXY(startPoint.x(), startPoint.y())
    point2 = QgsPointXY(startPoint.x(), endPoint.y())
    point3 = QgsPointXY(endPoint.x(), endPoint.y())
    point4 = QgsPointXY(endPoint.x(), startPoint.y())

    self.rubberBand.addPoint(point1, False)
    self.rubberBand.addPoint(point2, False)
    self.rubberBand.addPoint(point3, False)
    self.rubberBand.addPoint(point4, True)    # true to update canvas
    self.rubberBand.show()

  def rectangle(self):
    if self.startPoint is None or self.endPoint is None:
      return None
    elif (self.startPoint.x() == self.endPoint.x() or \
          self.startPoint.y() == self.endPoint.y()):
      return None

    return QgsRectangle(self.startPoint, self.endPoint)

  def deactivate(self):
    self.clearWorkLayers()
    self.reset()
    QgsMapTool.deactivate(self)
    self.deactivated.emit()


  def get_display_resolution(self):
      return self.canvas.extent().width()/self.canvas.width()

  def getLayerByTile(self,title):
      for layer in self.canvas.layers():
          if layer.name() == title:
              return layer
      return None

  def resetWorkingExtent(self):
      if not self.seg_enabled: return
      self.working_extent_layer=self.getLayerByTile("working_extent")
      if self.working_extent_layer is not None:
          QgsProject.instance().removeMapLayer(self.working_extent_layer.id())
          self.working_extent_layer = None
      if self.workingExtent is not None:
          self.segany.reset_image()
          self.workingExtent=None

  def setWorkingExtent(self, imgcrs_point):
      '''
      如果点击位置位于当前工作区内，就不更新范围；
      如果在当前工作区外，需要先结束前面的任务，并清空样点，再更新工作区，并开始后面的任务
      注意：可以利用canvasitem标画一个范围，提醒作业时尽可能先完成范围内的，再移动
      '''
      if not self.seg_enabled: return
      self.working_extent_layer=self.getLayerByTile("working_extent")
      if self.working_extent_layer is None:
          self.working_extent_layer=QgsVectorLayer('Polygon?crs=epsg:', 'working_extent', 'memory')
          layer_fields = QgsFields()
          layer_fields.append(QgsField('id', QVariant.Int))
          self.working_extent_layer.dataProvider().addAttributes(layer_fields)
          self.working_extent_layer.setCrs(self.monitask.wl.crs)
          self.working_extent_layer.updateFields()
          self.working_extent_layer.setFlags(QgsMapLayer.Private)

          #symbol = QgsLineSymbol.createSimple({'line_style': 'dash', 'color': 'red',"width ":"3"})
          symbol = QgsSymbol.defaultSymbol(self.working_extent_layer.geometryType())
          symL1 = QgsSimpleFillSymbolLayer.create({
              "outline_color": "200,200,255,255",
              "outline_width": "1",
              "line_style": "dot",
              "style": "no"
          })
          symbol.changeSymbolLayer(0, symL1)
          renderer = QgsInvertedPolygonRenderer(QgsSingleSymbolRenderer(symbol))
          # Define the renderer
          self.working_extent_layer.setRenderer(renderer)
          QgsProject.instance().addMapLayer(self.working_extent_layer)
      else:
          self.working_extent_layer.startEditing()
          self.working_extent_layer.dataProvider().truncate()
          self.working_extent_layer.commitChanges()

      if self.monitask.wl.baseimg_layer:
          #print_log("Current Base Image: ",self.monitask.wl.baseimg_layer.name())
          data_provider = self.monitask.wl.baseimg_layer.dataProvider()
          if len(data_provider.nativeResolutions())>0:
              self.native_resolution=data_provider.nativeResolutions()[0]
          else:
              self.native_resolution = data_provider.extent().width()/self.monitask.wl.baseimg_layer.width()

          cavas_resolution=self.get_display_resolution()
          data_provider = self.monitask.wl.baseimg_layer.dataProvider()
          cap=data_provider.providerCapabilities()

          if self.monitask.settingsObj.General_resolutionUsed==0:
              self.working_resolution=self.native_resolution
          elif self.monitask.settingsObj.General_resolutionUsed==1:
              if cavas_resolution<self.native_resolution*self.monitask.settingsObj.General_minResolutionZoom:
                  self.working_resolution = self.native_resolution*self.monitask.settingsObj.General_minResolutionZoom
              elif  cavas_resolution > self.native_resolution * self.monitask.settingsObj.General_maxResolutionZoom:
                  self.working_resolution = self.native_resolution*self.monitask.settingsObj.General_maxResolutionZoom
              else:
                  self.working_resolution = cavas_resolution
          else:
              self.working_resolution=self.native_resolution

          # if self.working_resolution>self.native_resolution and not (cap & QgsRasterDataProvider.ProviderHintBenefitsFromResampling):
          #     self.working_resolution = self.native_resolution

          offset=self.workImgSizePx*self.working_resolution/2
          self.workingExtent = QgsRectangle(imgcrs_point.x()-offset,imgcrs_point.y()-offset,imgcrs_point.x()+offset,imgcrs_point.y()+offset)

          print_log("Working Extent: \nnative_resolution,cavas_resolution,working_resolution,width:\n",self.native_resolution,cavas_resolution,self.working_resolution,self.workingExtent.width())

          # 将范围框添加要素到工作范围图层
          extent_feature = QgsFeature()
          extent_feature.setGeometry(QgsGeometry.fromRect(self.workingExtent))
          extent_feature.setAttributes([1])
          self.working_extent_layer.startEditing()
          self.working_extent_layer.addFeature(extent_feature)
          self.working_extent_layer.commitChanges()
          self.working_extent_layer.setExtent(self.workingExtent)

          self.refreshWorkingImage()

          # click_extent= QgsRectangle(click_point.x()-offset,click_point.y()-offset,click_point.x()+offset,click_point.y()+offset)
          # if self.workingExtent is None:
          #     self.workingExtent=click_extent
          #     self.refreshWorkingImage()
          # else:
          #     iou=self.calculate_iou(self.workingExtent,click_extent)
          #     if iou<0.33:
          #         self.workingExtent=click_extent
          #         self.refreshWorkingImage()

  def calculate_iou(self, extent1, extent2):
      if extent1.area()<=0.01: return 0
      x1, y1, w1, h1 = extent1.xMinimum(),extent1.yMinimum(),extent1.width(),extent1.height()
      x2, y2, w2, h2 = extent2.xMinimum(),extent2.yMinimum(),extent2.width(),extent2.height()

      # 计算矩形的面积
      area1 = w1 * h1
      area2 = w2 * h2

      # 计算矩形的交集
      xmin = max(x1, x2)
      ymin = max(y1, y2)
      xmax = min(x1 + w1, x2 + w2)
      ymax = min(y1 + h1, y2 + h2)
      inter_area = max(xmax - xmin, 0) * max(ymax - ymin, 0)
      # 计算IOU
      iou = inter_area / (area1 + area2 - inter_area)
      return iou

  def cutoutImageFromRasterLayer(self,rasterlayer,geo_extent,width_px,height_px):
      data=[]
      if rasterlayer:
          data_provider=rasterlayer.dataProvider()
          if str(rasterlayer.rasterType())=="RasterLayerType.SingleBandColorData":
              block=data_provider.block(1,geo_extent,width_px,height_px)
              data = np.array(block.data()).astype(np.uint8)
              data = data.reshape(block.height(), block.width(), 4)
              # QMessageBox.about(None, 'Message:SingleBandColorData', str(data.shape))
              data = data[:, :, 0:3]
              # QMessageBox.about(None, 'Message:SingleBandColorData', str(data.shape))
              #self.workingImg= np.transpose(data, (2, 0, 1))
          elif str(rasterlayer.rasterType())=="RasterLayerType.MultiBand":
              bands_data=[]
              for i in range(1,4):
                  block=data_provider.block(i,geo_extent,width_px,height_px)
                  bands_data.append(np.array(block.data()).astype(np.uint8).reshape(block.height(), block.width()))
              data=np.stack(bands_data)
              data=np.transpose(data, (1, 2, 0))
          return data
      else:
          return None

  def refreshWorkingImage(self):
      # import cv2
      if self.workingExtent:
          self.segany.reset_image()
          self.workingImg=self.cutoutImageFromRasterLayer(self.monitask.wl.baseimg_layer,self.workingExtent,self.workImgSizePx,self.workImgSizePx)
          # data_provider=self.monitask.wl.baseimg_layer.dataProvider()
          # if str(self.monitask.wl.baseimg_layer.rasterType())=="RasterLayerType.SingleBandColorData":
          #     block=data_provider.block(1,
          #         self.workingExtent,
          #         self.workImgSizePx,
          #         self.workImgSizePx)
          #
          #     data = np.array(block.data()).astype(np.uint8)
          #     data = data.reshape(block.height(), block.width(), 4)
          #     # QMessageBox.about(None, 'Message:SingleBandColorData', str(data.shape))
          #     data = data[:, :, 0:3]
          #     # QMessageBox.about(None, 'Message:SingleBandColorData', str(data.shape))
          #     #self.workingImg= np.transpose(data, (2, 0, 1))
          # elif str(self.monitask.wl.baseimg_layer.rasterType())=="RasterLayerType.MultiBand":
          #     bands_data=[]
          #     for i in range(1,4):
          #         block=data_provider.block(i,
          #             self.workingExtent,
          #             self.workImgSizePx,
          #             self.workImgSizePx)
          #         bands_data.append(np.array(block.data()).astype(np.uint8).reshape(block.height(), block.width()))
          #
          #     data=np.stack(bands_data)
          #     #QMessageBox.about(None, 'Message:MultiBand',str(data.shape))
          #     data=np.transpose(data, (1, 2, 0))
          #     #QMessageBox.about(None, 'Message:MultiBand',str(data.shape))

          # self.workingImg= data
          print_log(self.workingImg.shape,self.working_resolution,self.native_resolution)
          # cv2.imshow("working image", self.workingImg)
          self.segany.set_image(self.workingImg)

  def do_seg(self):
      '''
      todo: 将点击位置转换为工作影像的影像坐标，根据点击的左键（正样本）还是右键（负样本），加入样点列表，调用SAM，生成mask，并在临时图层中叠加显示mask
      '''
      if self.seg_enabled and len(self.click_points) > 0 and len(self.click_points_mode) > 0:
          print_log("Do_seg...")
          masks = self.segany.predict(self.click_points, self.click_points_mode)
          self.masks = masks
          self.updateMaskLayer()


  def adjust_mask(self,actType):
      if  self.masks is None:
          return
      if actType!=1 and actType!=2:
          return
      #QMessageBox.about(None, 'about1', "adjust_mask:"+str(actType)+"-"+str(self.masks))
      kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))  # 定义矩形结构元素
      kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))  # 定义矩形结构元素
      if actType==1:
          self.masks = cv2.dilate(self.masks, kernel, iterations=1)
      elif actType==2:
          self.masks = cv2.erode(self.masks, kernel2, iterations=1)
      self.updateMaskLayer()

  def updateMaskLayer(self):
      if  self.masks is None:
          return

      if self.temp_mask_layer:
          print_log("updateMaskLayer: remove .temp_mask_layer")
          QgsProject.instance().removeMapLayer(self.temp_mask_layer)

      #对生成的mask进行预处理，去除小的空洞和图斑(闭运算)，将边界适度扩展
      if type(self.monitask.settingsObj.Advanced_denoise_kernel_size)==int:
          denoise_kernel_siz=self.monitask.settingsObj.Advanced_denoise_kernel_size
      else:
          denoise_kernel_siz=eval(self.monitask.settingsObj.Advanced_denoise_kernel_size) if type(self.monitask.settingsObj.Advanced_denoise_kernel_size)==str else 5
      if type(self.monitask.settingsObj.Advanced_padding)==int:
          padding=self.monitask.settingsObj.Advanced_padding
      else:
          padding=eval(self.monitask.settingsObj.Advanced_padding) if type(self.monitask.settingsObj.Advanced_padding)==str else 3

      mask_result=self.masks.squeeze().astype("uint8")
      kernel1 = cv2.getStructuringElement(cv2.MORPH_RECT, (denoise_kernel_siz, denoise_kernel_siz))  # 定义矩形结构元素
      mask_result = cv2.morphologyEx(mask_result, cv2.MORPH_CLOSE, kernel1, iterations=1)
      kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (padding, padding))  # 定义矩形结构元素
      mask_result = cv2.dilate(mask_result, kernel2, iterations=1)
      self.masks=mask_result

      #根据mask，生成一个qgs的临时图层，用于显示
      # qgis:createconstantrasterlayer要求PIXEL_SIZE必须大于0.01，在经纬度坐标下，范围较小时，无法正常工作
      # params = {
      #     'EXTENT': self.workingExtent,
      #     'TARGET_CRS': self.monitask.wl.crs,
      #     'PIXEL_SIZE': self.working_resolution,
      #     'NUMBER': 0,
      #     'OUTPUT_TYPE': 0,
      #     'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
      # }
      # r = processing.run('qgis:createconstantrasterlayer', params)['OUTPUT']
      # print_log("updateMaskLayer: New temp_mask_layer")

      temp_mask_array = np.zeros((self.workImgSizePx, self.workImgSizePx), dtype=np.uint8)
      temp_mask_file=numpy_array_to_raster(temp_mask_array,(self.workingExtent.xMinimum(),self.workingExtent.yMaximum()),
                                           self.working_resolution,srs_wkid=int(self.monitask.wl.crs.authid()[5:]))

      self.temp_mask_layer = QgsRasterLayer(temp_mask_file, 'working_temp_mask', 'gdal')

      # h, w = self.masks.shape[-2:]
      # color = np.array([0, 0, 255])
      # mask_image = self.masks.reshape(h, w, 1) * color.reshape(1, 1, -1)
      # mask_image = mask_image.astype("uint8")
      # mask_image = cv2.cvtColor(mask_image, cv2.COLOR_BGR2RGB)
      # mask_image = cv2.addWeighted(self.workingImg, 0.5, mask_image, 0.9, 0)
      # cv2.imshow("mask",mask_image)

      self.temp_mask_layer.setExtent(self.workingExtent)
      provider = self.temp_mask_layer.dataProvider()
      # w = self.temp_mask_layer.width()
      # h = self.temp_mask_layer.height()

      dataType = provider.dataType(1)
      block = QgsRasterBlock(dataType, self.workImgSizePx, self.workImgSizePx)
       # 必须将np.ndarray用bytearray进行转换
      block.setData(bytearray(self.masks))

      provider.setEditable(True)
      provider.writeBlock(block, band=1)
      provider.setNoDataValue(1,0)
      provider.setEditable(False)
      provider.reload()

      mask_color=QColor(self.monitask.settingsObj.Advanced_mask_color)
      classesString = '1 {0} {1} {2} 255 1'.format(mask_color.red(),mask_color.green(),mask_color.blue())
      classes = QgsPalettedRasterRenderer.classDataFromString(classesString)
      rasterRenderer = QgsPalettedRasterRenderer(self.temp_mask_layer.dataProvider(), 1, classes)
      self.temp_mask_layer.setRenderer(rasterRenderer)
      if type(self.monitask.settingsObj.Advanced_mask_opacity) == str:
          self.monitask.settingsObj.Advanced_mask_opacity=eval(self.monitask.settingsObj.Advanced_mask_opacity)
      self.temp_mask_layer.renderer().setOpacity(self.monitask.settingsObj.Advanced_mask_opacity)

      self.temp_mask_layer.setFlags(QgsMapLayer.Private)
      print_log("updateMaskLayer: Add temp_mask_layer to canvas")
      QgsProject.instance().addMapLayer(self.temp_mask_layer)
      #self.canvas.refresh()

  def getLabelingFieldName(self):
      outFields = eval(str(self.monitask.settingsObj.General_outLayerFields))
      labelFieldName = None
      for field in outFields:
          if field[5] == "Labeling":
              labelFieldName = field[0]
      return labelFieldName

  def finish(self,labelAsLast=False):
      '''
      labelAsLast: true:表示使用最后一次用过的label作为本次提取图斑的label
      将生成的mask矢量化，放入内存临时图层，拷贝到剪切板，激活目标图层编辑状态和snapping设置，粘贴到目标图层中
      基本思路：用SAM生成Mask， 矢量化后保存在临时图层，然后copy到剪切板，再paste到目标图层中。paste之前，设置目标图层的相关snapping设置。
      注意avoid overlap失效的情况，有人反映当目标图层中如果存在无效geometry，可能会导致avoid overlap失效：https://github.com/qgis/QGIS/issues/48361
      '''
      if len(self.click_points) < 1 and len(self.click_points_mode) < 1: return
      self.click_points.clear()
      self.click_points_mode.clear()
      #print_log(type(eval(self.monitask.settingsObj.General_parcelMinArea)))
      if self.monitask.settingsObj.General_parcelMinArea:
          area_limit=self.monitask.settingsObj.General_parcelMinArea
      else:
          area_limit=400

      #最小面积按照像素计算
      area_limit=area_limit*self.working_resolution**2

      #将mask数据转换成一个带有坐标系统的gdal数据集
      raster_driver = gdal.GetDriverByName("MEM")
      mask_raster_dataset = raster_driver.Create("mask_raster", self.masks.shape[0], self.masks.shape[1], 1, gdal.GDT_Byte)
      x_res = self.working_resolution
      y_res = -self.working_resolution
      geo_transform = (self.workingExtent.xMinimum(), x_res, 0, self.workingExtent.yMaximum(), 0, y_res)
      mask_raster_dataset.SetGeoTransform(geo_transform)
      srs = osr.SpatialReference()
      srs.ImportFromEPSG(int(self.monitask.wl.crs.authid()[5:]))
      mask_raster_dataset.SetProjection(srs.ExportToWkt())
      mask_raster_dataset.GetRasterBand(1).WriteArray(self.masks.squeeze())
      mask_raster_dataset.FlushCache()
      mask_data = mask_raster_dataset.GetRasterBand(1)  # im_data的类型为osgeo.gdal.Band

      # 将栅格的mask转换为矢量的多边形
      # 创建一个ogr的内存矢量图层
      vector_driver = ogr.GetDriverByName("Memory")
      ogr_vector_dataset = vector_driver.CreateDataSource("mask_vector")
      geomtype = ogr.wkbMultiPolygon
      ogr_lyr = ogr_vector_dataset.CreateLayer("seg_polygon", srs=srs, geom_type=geomtype)
      ogr_lyr.CreateField(ogr.FieldDefn('value', ogr.OFTReal))
      #矢量化，存入到ogr的内存图层中
      gdal.FPolygonize(mask_data, mask_data, ogr_lyr, 0, [], None)

      #拷贝之前，对内存中qgs_layer的feature判断label，并进行整型处理
      #print_log(self.extending_labelid)
      if self.extending_labelid>=0:
          labelObj=self.monitask.lb.getLabelItemById(self.extending_labelid)
      elif labelAsLast and self.lastUsed_labelid>=0:
          labelObj = self.monitask.lb.getLabelItemById(self.lastUsed_labelid)
      else:
          labelObj=self.detectLabel()
      self.extending_labelid = -1
      #将ogrLayer转换为一个内存中的qgsLayer，以便于利用QGIS的功能,过程中根据labelObj指定的reshape rule 进行整形
      qgs_layer=self.convert_ogrLayer2qgsLayer(ogr_lyr,labelObj)
      #将内存中qgs_layer中的feature，拷贝到存放图斑的目标图层中，充分利用QGIS在这一过程中对snapping的控制机制
      #粘贴后，由于会和已有要素发生切割，形成一些小多边形或多多边形，需要打散并删除细碎多边形
      qgs_layer.selectAll()
      print_log("总计生成{}个图斑，将复制到目标图层....".format(qgs_layer.selectedFeatureCount()))
      qgs_layer.removeSelection()

      if self.monitask.wl.output_layer:
          try:
              self.monitask.wl.output_layer.featureDeleted.disconnect()
          except:
              pass
          self.monitask.wl.output_layer.removeSelection()
          self.monitask.wl.output_layer.featureDeleted.connect(self.clear_highlight_features)
          self.copyFeaturesTo(qgs_layer,self.monitask.wl.output_layer,minArea=area_limit)
          self.monitask.wl.output_layer.startEditing()
          remove_list = []
          selFeatures=self.monitask.wl.output_layer.selectedFeatures()
          featcount=self.monitask.wl.output_layer.selectedFeatureCount()
          print_log("复制粘贴面积大于{}的图斑到目标图层后，根据snapping设置自动完成叠盖裁剪处理后，产生{}个多边形或多部多边形".format(area_limit,featcount))
          new_features = []
          dataTypes = {"String": QVariant.String,
                       "Int": QVariant.Int,
                       "Integer": QVariant.Int,
                       "Double": QVariant.Double,
                       "Date": QVariant.String,
                       "DateTime": QVariant.String,
                       "Boolean": QVariant.Int}
          outFields = eval(str(self.monitask.settingsObj.General_outLayerFields))

          labelFieldName=None
          labelFieldType=None
          ccFieldName=None
          ccFieldType=None
          LSIDFieldName=None
          for field in outFields:
              if field[5]=="Labeling":
                  labelFieldName=field[0]
                  labelFieldType=field[1]
              elif field[5]=="Coding":
                  ccFieldName=field[0]
                  ccFieldType=field[1]
              elif field[5]=="LabelSytemIdentifying":
                  LSIDFieldName=field[0]

          #对细碎多边形进行筛选，删除不符合要求的(小、窄条等)
          for feature in selFeatures:
              remove_list.append(feature.id())
              geom = feature.geometry()
              #删除小于最小面积指标的空洞
              geom = geom.removeInteriorRings(minimumAllowedArea=area_limit)
              feat_area=geom.area()
              if feat_area<=0:continue

              # check if feature geometry is multipart
              if geom.isMultipart():
                  print_log("--------------------to refine the multi-part results --------------------- ")
                  parts_details=[]
                  #保留主要的：最大的，其他保留面积超过最小图斑指标，且非细条、面积占比超过10%的图斑
                  max_area=0
                  for part in geom.asGeometryCollection():
                      part_details={}
                      part_details["area"]=part.area()
                      if part_details["area"]<=0: continue

                      if part_details["area"]>max_area:
                          max_area=part_details["area"]
                      part_details["shape_index"]=4*3.1415926*part_details["area"]/part.length()**2
                      part_details["ratio"]=part_details["area"]/feat_area
                      part_details["feature"]=QgsFeature(feature)
                      part_details["feature"].setGeometry(part)
                      if labelFieldName:
                          part_details["feature"][labelFieldName]=str(labelObj.id) if labelFieldType=="String" else labelObj.id
                      if ccFieldName:
                          part_details["feature"][ccFieldName]=str(labelObj.cc) if ccFieldType=="String" else labelObj.cc
                      if LSIDFieldName:
                          ls_meta=self.monitask.lb.getMetaInfo()
                          part_details["feature"][LSIDFieldName] = ls_meta[0] if ls_meta else "NULL"

                      parts_details.append(part_details)
                  for part_detail in parts_details:
                      if part_detail["feature"].geometry().isMultipart():
                          print_log("***********The part is still another multipart one")
                      if part_detail["area"]==max_area:
                          new_features.append(part_detail["feature"])
                          self.monitask.setRecentUsedLabel(labelObj.title,labelObj.id)
                          self.monitask.incedentLabelUsedTimes(labelObj.id,1)
                      elif part_detail["area"]>area_limit and part_detail["ratio"]>0.2 and part_detail["shape_index"]>0.05:
                          new_features.append(part_detail["feature"])
                          self.monitask.setRecentUsedLabel(labelObj.title,labelObj.id)
                          self.monitask.incedentLabelUsedTimes(labelObj.id,1)
                  # add new features to layer
              else: #不是multipart的，如果粘贴的不止1个要素，则只保留不是特别狭长的条带，如果只有一个，由于是专门采集的，因此保留
                  print_log("--------------------to refine the single part results --------------------- ")
                  shape_index=4*3.1415926*feat_area/geom.length()**2
                  #QMessageBox.about(None, 'shape_index',"Index:{}".format(shape_index))
                  #如果只有一个，就放过，否则太狭长的过滤掉
                  #print_log("shape_index:",shape_index)
                  if featcount==1 or shape_index>0.05:
                      temp_feature=QgsFeature(feature)
                      temp_feature.setGeometry(geom)
                      if labelFieldName:
                          temp_feature[labelFieldName]=str(labelObj.id) if labelFieldType=="String" else labelObj.id
                          self.monitask.setRecentUsedLabel(labelObj.title,labelObj.id)
                          self.monitask.incedentLabelUsedTimes(labelObj.id,1)
                      if ccFieldName:
                          temp_feature[ccFieldName]=str(labelObj.cc) if ccFieldType=="String" else labelObj.cc
                      if LSIDFieldName:
                          ls_meta=self.monitask.lb.getMetaInfo()
                          temp_feature[LSIDFieldName] = ls_meta[0] if ls_meta else "NULL"
                          #print_log("maptool:monitask.lb.guid:", ls_meta[0])

                      new_features.append(temp_feature)
          # first remove the original features from layer
          if len(remove_list) > 0:
              for id in remove_list:
                  self.monitask.wl.output_layer.deleteFeature(id)
          self.monitask.wl.output_layer.commitChanges()

          #second align to the edges of existing features according to the project global snapping config
          current_snapConfig = QgsProject.instance().snappingConfig()
          align_torlerance = current_snapConfig.tolerance()
          if current_snapConfig.units()==QgsTolerance.Pixels:
              align_torlerance=align_torlerance*self.working_resolution

          distance_thresh = align_torlerance*1.2
          #print_log(" number of new_features: ",len(new_features))
          print_log("Aligning to neighbors...")
          for i in range(len(new_features)-1,-1,-1):
              this_geom=new_features[i].geometry()
              neib_feats=get_neigbor_features(this_geom,self.monitask.wl.output_layer,distance_thresh)
              nb_ids= [f.id() for f in neib_feats]
              print_log(i, str(len(nb_ids))+" neigbours")
              # 检查待插入的要素与其邻近图斑之间的缝隙如果小于容限值，就扩大待插入的要素，以向相邻图斑对齐
              aligned_geom = aligned_to_neighbors(this_geom, neib_feats, align_torlerance,self.working_resolution)
              if len(nb_ids)>0:
                  self.monitask.wl.output_layer.selectByIds(nb_ids,QgsVectorLayer.AddToSelection)

              #print_log("The area of the geometry: before aligned: {}, After aligned: {}".format(this_geom.area(),aligned_geom.area()))
              merged2nb=False  #是否并入相邻同类图斑
              # #以下部分可以考虑全部通过dissolve_features解决，需要将所有neibors都选中。
              # if len(neib_feats)>0:
              #     for nb in neib_feats:
              #         # 检查待插入的要素与其邻接图斑是否同类，如果同类，且同类面积小于阈值或并入的面积占比很小(10%)，就合并到同类图斑中
              #         nb_area=nb.geometry().area()
              #         new_area=aligned_geom.area()
              #         # print_log("Touch? {}, label:{}/{}, neibor Area:{}".format(aligned_geom.touches(nb.geometry()),new_features[i][labelFieldName],nb[labelFieldName],nb.geometry().area()))
              #         # print_log("Disjoint? {}, distance:{}".format(aligned_geom.disjoint(nb.geometry()),aligned_geom.distance(nb.geometry())))
              #         # print_log("Intersects? {}".format(aligned_geom.intersects(nb.geometry())))
              #         # print_log("Overlaps? {}".format(aligned_geom.overlaps(nb.geometry())))
              #         # sharedPaths=aligned_geom.sharedPaths(nb.geometry())
              #         # print_log("SharedPath length: {}".format(sharedPaths.length()))
              #         #print_log("Merging...........................", type(new_features[i][labelFieldName]), type(nb[labelFieldName]),new_features[i][labelFieldName]==nb[labelFieldName])
              #         #print_log(nb_area,new_area/nb_area,not aligned_geom.disjoint(nb.geometry()),new_features[i][labelFieldName] ,nb[labelFieldName])
              #         if not aligned_geom.disjoint(nb.geometry()) \
              #                 and new_features[i][labelFieldName] == nb[labelFieldName] and nb_area < 100000000:
              #                 #and (nb_area < 100000000 or new_area/nb_area<0.5):
              #             new_geom = aligned_geom.combine(nb.geometry())
              #             if new_geom.isMultipart():
              #                 print_log("***Note: The merged result polygon is multipart, perhaps it will be totally removed (To be fixed).")
              #
              #             print_log("Area after combined with {}: {}".format(nb["fid"],new_geom.area()))
              #             new_geom.removeDuplicateNodes(epsilon=self.working_resolution/2)
              #             print_log("Area after removeDuplicateNodes:",new_geom.area())
              #             new_geom=new_geom.makeValid()
              #             print_log("Area after makeValid:",new_geom.area())
              #             new_geom=self.clear_invalid_vertex(new_geom)
              #             print_log("Area after clear_invalid_vertex:",new_geom.area())
              #
              #             if new_geom.area()>0:
              #                 print_log("Merged feature {}({},geoType:{}) into existing {}, waiting update...".format(i,new_geom.type(),new_geom.wkbType(), nb["fid"]))
              #                 self.monitask.wl.output_layer.startEditing()
              #                 self.monitask.wl.output_layer.changeGeometry(nb["fid"], new_geom)
              #                 self.monitask.wl.output_layer.commitChanges()
              #                 new_features.pop(i)
              #                 self.monitask.wl.output_layer.select(nb["fid"])
              #                 merged2nb=True
              #                 break
              #             else:
              #                 print_log("***Note: The merged result polygon is invalid, omit the merge, continue to check with the next neighbor.")

              #如果没有并入相邻同类图斑，检查有效性，清理奇异点
              #if not merged2nb:
              aligned_geom = self.clear_invalid_vertex(aligned_geom.makeValid())
              new_features[i].setGeometry(aligned_geom)
              #print_log("Area after clear_invalid_vertex and makeValid :", aligned_geom.area())

          #print_log(" number of new_features after combined: ",len(new_features))
          self.monitask.wl.output_layer.featureAdded.connect(self.outputLayer_added_feature)
          if len(new_features)>0:
              self.monitask.wl.output_layer.startEditing()
              self.monitask.wl.output_layer.addFeatures(new_features)
              self.monitask.wl.output_layer.commitChanges()
          #如果存在与相邻图斑合并的情况，可能没有合并干净，统一做一次处理(需要将相邻图斑全部选择加进来)
          self.dissolve_features(fieldName=labelFieldName,fieldValue=labelObj.id)
          self.monitask.wl.output_layer.featureAdded.disconnect(self.outputLayer_added_feature)

          self.highlight_features()
          if self.temp_mask_layer:
              # self.temp_mask_layer.renderer().setOpacity(0.2)
              QgsProject.instance().layerTreeRoot().findLayer(self.temp_mask_layer.id()).setItemVisibilityChecked(False)
          self.click_crs_points.clear()
          self.extend_segment(labelObj.id)
          self.monitask.wl.output_layer.removeSelection()
          self.monitask.wl.output_layer.featureDeleted.connect(self.feature_deleted)
          self.lastUsed_labelid=labelObj.id
          #print_log("--------------------refined the result --------------------- ")
      else:
          QMessageBox.about(None, 'Notice', "未设定存放采集结果的图层，请选择并正确设置Snapping")
      mask_raster_dataset=None

  def dissolve_features(self,fieldName,fieldValue):
      if fieldName is None or fieldValue is None:
          return
      if self.monitask.wl.output_layer.selectedFeatureCount()<=1:
          return
      if type(fieldValue)==str:
          expression = '\"{}\" = "{}"'.format(fieldName,fieldValue)
      else:
          expression = '\"{}\" = {}'.format(fieldName,fieldValue)
      selected_ids=self.monitask.wl.output_layer.selectedFeatureIds()
      print_log("ids of neibours and new_features:",selected_ids)
      self.monitask.wl.output_layer.selectByExpression(expression, QgsVectorLayer.IntersectSelection)
      intersect_ids = self.monitask.wl.output_layer.selectedFeatureIds()
      print_log("ids of the same label as {} in previous selected:{}".format(fieldValue,intersect_ids))
      #other_ids=list(set(selected_ids)-set(intersect_ids))
      fs = list(self.monitask.wl.output_layer.selectedFeatures())  # fs: features
      # combine selected geometries
      if len(fs)>1:
          print_log("dissolving the features with lable {}...".format(fieldValue))
          g = fs[0].geometry()
          for i in range(len(fs) - 1):
              g = fs[i + 1].geometry().combine(g)
          self.monitask.wl.output_layer.featureAdded.connect(self.outputLayer_added_feature)
          self.monitask.wl.output_layer.startEditing()
          if g.isMultipart():
              parts= g.asGeometryCollection()
              print_log("origin {} features, dissolving result has {} parts ...".format(len(fs),len(parts)))
              #if len(parts)<len(fs):#合并图斑数变少，否则还不如不合并
              for part in parts:
                  #print_log(fs[0].fields(),fs[0].attributes())
                  part=self.clear_invalid_vertex(part.makeValid())
                  new_feature = QgsFeature()
                  new_feature.setFields(self.monitask.wl.output_layer.fields())
                  new_feature.setGeometry(part)
                  n_att= len(fs[0].attributes())
                  for i in range(1,n_att):
                      #print_log(fs[0][i])
                      new_feature[i]=fs[0][i]
                  self.monitask.wl.output_layer.addFeature(new_feature)
              self.monitask.wl.output_layer.deleteFeatures(intersect_ids)
          else:
              print_log("origin {} features, dissolving result as 1".format(len(fs)))
              #print_log(fs[0].fields(), fs[0].attributes())
              g = self.clear_invalid_vertex(g.makeValid())
              new_feature = QgsFeature()
              new_feature.setFields(self.monitask.wl.output_layer.fields())
              new_feature.setGeometry(g)
              n_att = len(fs[0].attributes())
              for i in range(1, n_att):
                  new_feature[i] = fs[0][i]
              self.monitask.wl.output_layer.addFeature(new_feature)
              self.monitask.wl.output_layer.deleteFeatures(intersect_ids)
          self.monitask.wl.output_layer.commitChanges()
          self.monitask.wl.output_layer.featureAdded.disconnect(self.outputLayer_added_feature)
      #self.monitask.wl.output_layer.selectByIds(other_ids,QgsVectorLayer.AddToSelection)

  def feature_deleted(self, fid):
      for feature in self.monitask.wl.output_layer.dataProvider().getFeatures(QgsFeatureRequest(fid)):
          #print_log(feature.attributes())
          self.monitask.lb.delLabelSamplesOfFeature(self.monitask.wl.output_layer.name(),feature.id())

  def clear_invalid_vertex(self,geometry):
      def distance(v1,v2):
          d=math.sqrt((v1.x() - v2.x()) **2 + (v1.y() - v2.y())**2)
          if d==0:
              d=0.00000001
          return d

      vertices=[v for v in geometry.vertices()]
      d={}
      #print_log("count of vertices: ",len(vertices))
      for  i in range(len(vertices)-1):
          if i==len(vertices)-2:
              d[i] = {i + 1: distance(vertices[i], vertices[i + 1])}
          else:
              d[i]={
                  i+1:distance(vertices[i],vertices[i+1]),
                  i+2:distance(vertices[i],vertices[i+2])
                  }
      for i in range(len(vertices)-2,0,-1):
          cos= (d[i-1][i+1]**2 - d[i][i+1]**2 - d[i-1][i]**2) / (-2 * d[i][i+1] * d[i-1][i])
          if cos > 0.98:  # angle<9.8度
              geometry.deleteVertex(i)
          # print_log("Odd Point and the Cos(Angle):", i, cos)
          # cos = 1 if cos>1 else cos
          # cos = -1 if cos<-1 else cos
          # print_log("angle at {} ({},{}) is {}".format(i, vertices[i].x(), vertices[i].y(), math.degrees(math.acos(cos))))
      return geometry


  def outputLayer_added_feature(self, id):
      self.monitask.wl.output_layer.selectByIds([id], Qgis.SelectBehavior.AddToSelection)

  def highlight_features(self):
      self.latest_ids_added.clear()
      self.clear_highlight_features()
      maxarea_featid=-1
      maxarea=0
      for feat in self.monitask.wl.output_layer.selectedFeatures():
          h = QgsHighlight(self.canvas, feat, self.monitask.wl.output_layer)
          feat_area=feat.geometry().area()
          #get id of the biggest feature, to fill the "featid" of the corresponding labelsample
          if feat_area>maxarea:
              maxarea=feat_area
              maxarea_featid=feat["fid"]
              self.latest_parcel_centroid = feat.geometry().centroid().asPoint()

          self.latest_ids_added.append(feat["fid"])
          # set highlight symbol properties
          h.setColor(QColor(255, 255, 0, 255))
          h.setWidth(6)
          h.setFillColor(QColor(255, 255, 255, 100))
          self.highlightItems.append(h)
      if self.latest_inserted_sample_id>0:
          self.monitask.lb.updatelabelSampleFeatid(self.latest_inserted_sample_id,maxarea_featid)

  def clear_highlight_features(self):
      for h in self.highlightItems:
          self.canvas.scene().removeItem(h)
      self.highlightItems.clear()

  def create_debug_layer(self,geo_type="linestring"):
      '''
      创建一个临时的内存图层，用于显示临时生成的一些feature
      '''
      layer_fields = QgsFields()
      layer_fields.append(QgsField('angle', QVariant.Double))
      if geo_type=="point":
          self.debug_layer_point = QgsVectorLayer(geo_type + '?crs=' + self.monitask.wl.crs.authid(),'debug_layer_' + geo_type, 'memory')
          self.debug_layer_point.dataProvider().addAttributes(layer_fields)
          self.debug_layer_point.setCrs(self.monitask.wl.crs)
          self.debug_layer_point.updateFields()
          symbol = QgsMarkerSymbol.createSimple({'name': 'arrow', "angle": "0",
                                                 "cap_style": "round", "joinstyle": "round",
                                                 "outline_width": "1", "outline_width_unit": "Point",
                                                 "horizontal_anchor_point": "1", "vertical_anchor_point": "2",
                                                 'color': "255,234,0,255", "outline_color": "234,17,21,255",
                                                 "size": "10", 'size_unit': 'Point'})
          symbol.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyAngle,QgsProperty.fromExpression('angle'))

          renderer = QgsSingleSymbolRenderer(symbol)
          self.debug_layer_point.setRenderer(renderer)
          self.debug_layer_point.setFlags(QgsMapLayer.Private)
          QgsProject.instance().addMapLayer(self.debug_layer_point)
      elif geo_type=="linestring":
          symbol = QgsLineSymbol.createSimple({'line_style': 'dash', 'color': 'red',"width ":"3"})
          renderer = QgsSingleSymbolRenderer(symbol)
          self.debug_layer_line = QgsVectorLayer(geo_type + '?crs=' + self.monitask.wl.crs.authid(),'debug_layer_' + geo_type, 'memory')
          self.debug_layer_line.dataProvider().addAttributes(layer_fields)
          self.debug_layer_line.setCrs(self.monitask.wl.crs)
          self.debug_layer_line.updateFields()
          self.debug_layer_line.setRenderer(renderer)
          self.debug_layer_line.setFlags(QgsMapLayer.Private)
          QgsProject.instance().addMapLayer(self.debug_layer_line)
      elif geo_type=="polygon":
          self.debug_layer_polygon = QgsVectorLayer(geo_type + '?crs=' + self.monitask.wl.crs.authid(),
                                                    'debug_layer_' + geo_type, 'memory')
          self.debug_layer_polygon.dataProvider().addAttributes(layer_fields)
          self.debug_layer_polygon.setCrs(self.monitask.wl.crs)
          self.debug_layer_polygon.updateFields()
          symbol = QgsSymbol.defaultSymbol(self.debug_layer_polygon.geometryType())
          symL1 = QgsSimpleFillSymbolLayer.create({
              "outline_color": "0,0,255,255",
              "outline_width": "0.5",
              "line_style": "dot",
              "style": "no"
          })
          symbol.changeSymbolLayer(0, symL1)
          renderer = QgsInvertedPolygonRenderer(QgsSingleSymbolRenderer(symbol))
          self.debug_layer_polygon.setRenderer(renderer)
          self.debug_layer_polygon.setFlags(QgsMapLayer.Private)
          QgsProject.instance().addMapLayer(self.debug_layer_polygon)
      # Define the renderer
  def show_geometry_in_debuglayer(self,geometry,marker_angle=0):
      feature = QgsFeature()
      feature.setGeometry(geometry)
      feature.setAttributes([marker_angle])
      # print_log("In show_geometry_in_debuglayer:",geometry.type())
      if geometry.type()==QgsWkbTypes.GeometryType.Point:
          if self.debug_layer_point is None:
              self.create_debug_layer(geo_type="point")
          else:
              self.clear_layer_features(self.debug_layer_point)
          self.debug_layer_point.startEditing()
          self.debug_layer_point.dataProvider().addFeature(feature)
          self.debug_layer_point.updateExtents()
          self.debug_layer_point.commitChanges()

      elif geometry.type()==QgsWkbTypes.GeometryType.Line:
          if self.debug_layer_line is None:
              self.create_debug_layer(geo_type="linestring")
          else:
              self.clear_layer_features(self.debug_layer_line)
          self.debug_layer_line.startEditing()
          self.debug_layer_line.dataProvider().addFeature(feature)
          self.debug_layer_line.updateExtents()
          self.debug_layer_line.commitChanges()
      elif geometry.type()==QgsWkbTypes.GeometryType.Polygon:
          if self.debug_layer_polygon is None:
              self.create_debug_layer(geo_type="polygon")
          else:
              self.clear_layer_features(self.debug_layer_polygon)
          self.debug_layer_polygon.startEditing()
          self.debug_layer_polygon.dataProvider().addFeature(feature)
          self.debug_layer_polygon.updateExtents()
          self.debug_layer_polygon.commitChanges()

  def clear_layer_features(self,vectorlayer):
      if vectorlayer:
          vectorlayer.startEditing()
          vectorlayer.selectAll()
          vectorlayer.deleteSelectedFeatures()
          vectorlayer.commitChanges()

  def extend_segment(self,labelid):
      def get_extending_point(base_line,extent_polygon):
          startp=base_line.centroid()
          baseLine_buffer=base_line.buffer(4*self.working_resolution,1)
          extending_point=baseLine_buffer.difference(extent_polygon).pointOnSurface()
          dis=startp.distance(extending_point)
          startp=startp.asPoint()
          endp=extending_point.asPoint()
          print_log(endp.y()-startp.y(),dis,(endp.y()-startp.y())/dis)
          angle=math.degrees(math.acos((endp.y()-startp.y())/dis))
          if endp.x()-startp.x()<0:
              angle=-1*angle
          return extending_point,angle

      extent_polygon=QgsGeometry.fromRect(self.workingExtent)
      geom_polygons=QgsGeometry.collectGeometry([f.geometry() for f in self.monitask.wl.output_layer.selectedFeatures()])
      geom_lines = geom_polygons.convertToType(QgsWkbTypes.GeometryType.LineGeometry)
      extent_edge = QgsGeometry.fromRect(self.workingExtent).buffer(-2*self.working_resolution, 1).convertToType(QgsWkbTypes.GeometryType.LineGeometry)
      share_edge = geom_polygons.intersection(extent_edge)
      print_log("Trying to extend segment....segResult_length:",geom_lines.length(),"\nInfo about shared edge:\nis Multipart? Geom_type,isNul/Empty,Shared_Area,Shared_length:\n",
            share_edge.isMultipart(),share_edge.type(),(share_edge.isNull() or share_edge.isEmpty()),share_edge.area(),share_edge.length())

      #self.clear_layer_features(self.debug_layer_point)
      # self.clear_layer_features(self.debug_layer_line)
      # self.clear_layer_features(self.debug_layer_polygon)
      inner_extending_points=[]
      outter_extending_points=[]
      if share_edge.isMultipart():
          for part in share_edge.asGeometryCollection():
              # print_log("Part:",part.type(),part.area(),part.length())
              extending_point,angle=get_extending_point(part,extent_polygon)
              circle=extending_point.buffer(6*self.working_resolution,5).convertToType(QgsWkbTypes.GeometryType.LineGeometry)
              # 寻找最佳的判断方式
              # print_log(circle.touches(geom_lines),circle.touches(geom_polygons))
              # print_log(circle.intersects(geom_lines),geom_lines.intersects(circle),circle.intersects(geom_polygons),geom_polygons.intersects(circle))
              # print_log(circle.overlaps(geom_lines),geom_lines.overlaps(circle),circle.overlaps(geom_polygons),geom_polygons.overlaps(circle))
              # print_log(circle.disjoint(geom_lines),geom_lines.disjoint(circle),circle.disjoint(geom_polygons),geom_polygons.disjoint(circle))
              # print_log(circle.crosses(geom_lines),geom_lines.crosses(circle),circle.crosses(geom_polygons),geom_polygons.crosses(circle))

              if circle.crosses(geom_polygons):
                  if extending_point.within(geom_polygons): #扩展点还是位于已有多边形内部，可能并不是真正的扩展点，作为候选按使用
                      inner_extending_points.append(extending_point)
                  else: #位于已有多边形外部，属于真正的扩展点
                      print_log("Not inside the existing polygon, Near the edge")
                      outter_extending_points.append(extending_point)
                  self.show_geometry_in_debuglayer(extending_point,angle)
                  #self.show_geometry_in_debuglayer(part)
                  #self.show_geometry_in_debuglayer(extending_point.buffer(6 * self.working_resolution, 5))
              else:
                  print_log("The part is inside the existing polygon")
      elif not (share_edge.isNull() or share_edge.isEmpty()):
          extending_point,angle = get_extending_point(share_edge, extent_polygon)
          circle = extending_point.buffer(6*self.working_resolution, 5).convertToType(QgsWkbTypes.GeometryType.LineGeometry)
          if circle.crosses(geom_polygons):
              if extending_point.within(geom_polygons):
                  inner_extending_points.append(extending_point)
              else:
                  outter_extending_points.append(extending_point)
              self.show_geometry_in_debuglayer(extending_point,angle)
              # self.show_geometry_in_debuglayer(share_edge)
              # #self.show_geometry_in_debuglayer(extending_point.buffer(6 * self.working_resolution, 5))
          else:
             print_log("The share_edge is inside the existing polygon")

      all_extending_points=[outter_extending_points,inner_extending_points]
      for extending_points in all_extending_points:#优先处理明确属于扩展区的点
          if len(extending_points)>0:
              geom_points = QgsGeometry.collectGeometry(extending_points)
              bbox=geom_points.boundingBox()
              if len(extending_points)>1 and bbox.width()<self.workingExtent.width() and bbox.height()<self.workingExtent.height():
                      ext_center=geom_points.centroid().asPoint()
                      self.setWorkingExtent(ext_center)
                      self.canvas.setCenter(ext_center)
                      self.click_points.extend([self.toWorkingExtentCoordinates(ex_point.asPoint()) for ex_point in extending_points])
                      self.click_crs_points.extend([ex_point.asPoint() for ex_point in extending_points])
              else:
                  import random
                  random_point=extending_points[random.randint(0,len(extending_points)-1)].asPoint()
                  self.setWorkingExtent(random_point)
                  self.canvas.setCenter(random_point)
                  self.click_crs_points.append(random_point)
                  self.click_points.append(self.toWorkingExtentCoordinates(random_point))
              #set the label as positive prompt 
              self.click_points_mode.clear()
              self.click_points_mode=[1]*len(self.click_points)
              print_log("Doing extending seg...")
              self.extending_labelid = labelid
              self.do_seg()

  def get_max_similarity_with(self,labelids,this_gebd,this_lebd):
      gpca_similarity=0
      lpca_similarity=0
      gagent_similarity=0
      lagent_similarity=0
      result=0
      resultid=-1
      agentsAndPcas = self.monitask.lb.getLabelsAgentsPcaByIds(labelids)
      if len(agentsAndPcas)>0:
          for labelid in labelids:
              if labelid not in agentsAndPcas: continue
              if agentsAndPcas[labelid][0] is not None:
                  gagent_similarity = self.calc_similarity(this_gebd, this_lebd, agentsAndPcas[labelid][0])
              if agentsAndPcas[labelid][1] is not None:
                  lagent_similarity = self.calc_similarity(this_gebd, this_lebd, agentsAndPcas[labelid][1])
              if agentsAndPcas[labelid][2] is not None:
                  gpca_similarity=self.calc_similarity(this_gebd,this_lebd,[agentsAndPcas[labelid][2]])
              if agentsAndPcas[labelid][3] is not None:
                  lpca_similarity=self.calc_similarity(this_gebd,this_lebd,[agentsAndPcas[labelid][3]])
              similarity=max([gpca_similarity,lpca_similarity,gagent_similarity,lagent_similarity])
              if similarity>result:
                  result=similarity
                  resultid=labelid
      return result,resultid

  def detectLabel(self):
      '''
      Todo: detect the label of the target feature(use the lagest) in the layer based on the existing results recorded in Label BAse
      if none acceptable, let the user select or create a new label for it.
      Step1: create sample images and computing their ebbedings  in several scales
      step2: get existing labels
          step3: computing the similarities between sample and existing labels
          step4: refresh the label list according to the  result similarities
          step5: choose the best and promote the user the selected result if user prefer to know when the optional label is available
            step5.1: if no optional label available, list all labels and promote the user choose one or create a new one
       以上3步可优化为：按照最近使用、使用频次的优先顺序，选择备选label进行计算，如果相似性大于某一阈值，即可确定结果，不需要针对所有类计算相似性
      step6: refineShape of the feature geometries according to determined label
      step7: assign the result, and return
      '''
      print_log("Detecting label...")
      if type(self.monitask.settingsObj.Advanced_oneshot_threshold)==int:
          oneshot_similariy_threshold = int(self.monitask.settingsObj.Advanced_oneshot_threshold)
      else:
          oneshot_similariy_threshold = 90

      if type(self.monitask.settingsObj.Advanced_candidate_threshold)==int:
          candidate_similariy_threshold = int(self.monitask.settingsObj.Advanced_candidate_threshold)
      else:
          candidate_similariy_threshold=66

      #step1.1
      g_sample,l_sample=self.clip_img_by_mask()
      #step1.2
      gebd=self.monitask.encoder.get_embedding(g_sample)
      lebd=self.monitask.encoder.get_embedding(l_sample)

      #step2
      candi_dict={}
      result_labeid=-1
      max_sim_labelid=-1
      max_similarity=0
      similarity = 0
      label_item=self.monitask.getRecentUsedLabel(minutes_passed=30)
      if label_item is not None:
          similarity,_=self.get_max_similarity_with([label_item.id],gebd,lebd)

      if similarity > max_similarity:
          max_similarity = similarity
          max_sim_labelid = label_item.id
      if similarity >= candidate_similariy_threshold and similarity < oneshot_similariy_threshold:
          candi_dict[label_item.id]=(label_item.id, label_item.title, similarity)

      if similarity>=oneshot_similariy_threshold:
          result_labeid=label_item.id
      else: #获取最常用label作为候选label
          label_items = self.monitask.getMostUsedLabels(min_used=5)
          if type(label_items) == list and len(label_items)>0:
              #计算与候选Label的agents和pca的最大相似性
              similarity,max_labelid=self.get_max_similarity_with([label_item.id for label_item in label_items],gebd,lebd)
              if similarity > max_similarity:
                  max_similarity = similarity
                  max_sim_labelid = max_labelid
              label_item=label_items[0]
              if max_labelid>-1:
                  for item in label_items:
                      if item.id==max_labelid:
                          label_item=item
              if similarity >= candidate_similariy_threshold and similarity < oneshot_similariy_threshold:
                  if label_item.id not in candi_dict or similarity>candi_dict[label_item.id][2]:
                      candi_dict[label_item.id] = (label_item.id, label_item.title, similarity)

              if similarity >= oneshot_similariy_threshold:
                  result_labeid = label_item.id
              else:#计算当前样本与候选Label对应已有随机limit个实际样本的相似性的最大值
                  for label_item in label_items:
                      label_samples = self.monitask.lb.getLabelSamplesByLabelId(label_item.id, limit=5)
                      similarity = self.calc_similarity(gebd, lebd, label_samples)
                      if similarity > max_similarity:
                          max_similarity = similarity
                          max_sim_labelid = label_item.id
                      if similarity >= candidate_similariy_threshold and similarity < oneshot_similariy_threshold:
                          if label_item.id not in candi_dict or similarity > candi_dict[label_item.id][2]:
                              candi_dict[label_item.id] = (label_item.id, label_item.title, similarity)

                      if similarity >= oneshot_similariy_threshold:
                          result_labeid = label_item.id

      if max_similarity>=oneshot_similariy_threshold:
          result_labeid=max_sim_labelid

      candidates=candi_dict.values()
      result_labelObj=None
      if result_labeid>-1: #有达到阈值的，直接使用
          result_labelObj=self.monitask.lb.getLabelItemById(result_labeid)
          self.monitask.labelWidget.showKeyStatus("{}(id={},sim={:.2f})".format(result_labelObj.title,result_labelObj.id, max_similarity))
          print_log("Label Detected: labelid={}, labelTitle={}, similarity={}".format(result_labelObj.id, result_labelObj.title,max_similarity))
      elif len(candidates)>0: #没有最优的，但有一些可选的
          self.monitask.labelWidget.fillCadidateLabels(candidates)
          print_log("Waiting for user choosing label from the candidates.............")
          result_labelObj=self.monitask.labelWidget.getLabelItemFromCandidates(wait_seconds=60000)
      else: #没有推荐的，也可以从全集列表中选择
          print_log("Waiting for user choosing label from the full list.............")
          result_labelObj=self.monitask.labelWidget.getLabelItemFromCandidates(wait_seconds=60000)

      if result_labelObj is None:
          result_labelObj=self.monitask.labelWidget.newLabelItem()
          print_log("No proper existing label, new one: labelid={}, labelTitle={}".format(result_labelObj.id, result_labelObj.title))

      #将图片和embeddings的大小也记录下来，看看同一类别不同大小样本图片生成的embedding之间的相似性受样本快大小影响的情况
      self.latest_inserted_sample_id=-1
      labelSample = LabelSample(result_labelObj.id,l_sample,gebd.numpy(),lebd.numpy())
      labelSample.set_source(self.monitask.wl.output_layer.name(),-1,)
      labelSample.set_sizeinfo(g_sample.shape[0],g_sample.shape[1],l_sample.shape[0])
      lblgpca, lbllpca = self.monitask.lb.getLabelPCA(result_labelObj.id)
      if lblgpca is not None:
          labelSample.set_simpca(cosine_similarity(lblgpca,gebd),cosine_similarity(lbllpca,lebd))
      labelSample.set_entropy(get_entropy(g_sample),get_entropy(l_sample))
      labelSample.set_histogram(rgb_histogram(g_sample),rgb_histogram(l_sample))
      labelSample.set_image_meta(None,self.native_resolution,None,self.working_resolution)
      if len(self.click_crs_points)==1:
          samp_center=self.click_crs_points[0]
      else:
          samp_center = QgsGeometry.fromMultiPointXY(self.click_crs_points).pointOnSurface().asPoint()
      labelSample.set_position(samp_center.x(),samp_center.y())
      labelSample.set_selfsim(cosine_similarity(gebd, lebd),cosine_similarity(labelSample.ghis, labelSample.lhis))
      self.latest_inserted_sample_id=self.monitask.lb.insertLabelSample(labelSample)

      #print_log("Detected Label: {},{}".format(result_labelObj.id,result_labelObj.title))
      #print_log("Similarity of lebd and gebd: {}".format(self.calc_similarity(gebd,lebd, [labelSample])))

      return result_labelObj

  def calc_similarity(self,gebd: np.ndarray,lebd: np.ndarray, label_samples: list) -> float:
      sim_results=[]
      count=len(label_samples) if isinstance(label_samples,list) else label_samples.shape[0]
      if count>0:
          for sample in label_samples:
              if isinstance(sample,LabelSample):
                  sim_g_g=cosine_similarity(gebd,sample.gebd)
                  #sim_g_l=cos_sim(gebd,sample.lebd1)
                  #sim_l_g=cos_sim(lebd,sample.gebd)
                  sim_l_l=cosine_similarity(lebd,sample.lebd1)
                  #print_log(sample.labelid,sim_g_g,sim_l_l)
                  sim_results.append(sim_g_g)
                  #sim_results.append(sim_g_l)
                  #sim_results.append(sim_l_g)
                  sim_results.append(sim_l_l)
              elif type(sample)==np.ndarray:
                  sim_results.append(cosine_similarity(gebd,sample))
                  sim_results.append(cosine_similarity(lebd,sample))
          return max(sim_results)
      else:
          return 0

  def convert_ogrLayer2qgsLayer(self,ogr_Layer,labelObj):
      '''
      同时做整形
      '''
      if type(self.monitask.settingsObj.General_parcelMinArea)==int:
          area_limit=self.monitask.settingsObj.General_parcelMinArea
      else:
          area_limit= eval(self.monitask.settingsObj.General_parcelMinArea) if type(self.monitask.settingsObj.General_parcelMinArea)==str else 400

      if type(self.monitask.settingsObj.Advanced_simplify_torlerance)==int:
          simplify_torlerance = self.monitask.settingsObj.Advanced_simplify_torlerance
      else:
          simplify_torlerance = eval(self.monitask.settingsObj.Advanced_simplify_torlerance) if type(self.monitask.settingsObj.Advanced_simplify_torlerance)==str else 1

      if type(self.monitask.settingsObj.Advanced_ortho_torlerance)==float:
          ortho_torlerance = self.monitask.settingsObj.Advanced_ortho_torlerance
      else:
          ortho_torlerance = eval(self.monitask.settingsObj.Advanced_ortho_torlerance) if type(self.monitask.settingsObj.Advanced_ortho_torlerance)==str else 1e-08

      if type(self.monitask.settingsObj.Advanced_ortho_angleThreshold)==int:
          ortho_angleThreshold = self.monitask.settingsObj.Advanced_ortho_angleThreshold
      else:
          ortho_angleThreshold = eval(self.monitask.settingsObj.Advanced_ortho_angleThreshold) if type(self.monitask.settingsObj.Advanced_ortho_angleThreshold)==str else 20

      if type(self.monitask.settingsObj.Advanced_snap2grid_hspace) == int:
          snap2grid_hspace = self.monitask.settingsObj.Advanced_snap2grid_hspace
      else:
          snap2grid_hspace = eval(self.monitask.settingsObj.Advanced_snap2grid_hspace) if type(self.monitask.settingsObj.Advanced_snap2grid_hspace)==str else 1

      if type(self.monitask.settingsObj.Advanced_snap2grid_vspace) == int:
          snap2grid_vspace = self.monitask.settingsObj.Advanced_snap2grid_vspace
      else:
          snap2grid_vspace = eval(self.monitask.settingsObj.Advanced_snap2grid_vspace) if type(self.monitask.settingsObj.Advanced_snap2grid_vspace)==str else 1

      if type(self.monitask.settingsObj.Advanced_smooth_iterations) == int:
          smooth_iterations = self.monitask.settingsObj.Advanced_smooth_iterations
      else:
          smooth_iterations = eval(self.monitask.settingsObj.Advanced_smooth_iterations) if type(self.monitask.settingsObj.Advanced_smooth_iterations)==str else 1

      if type(self.monitask.settingsObj.Advanced_smooth_offset) == float:
          smooth_offset = self.monitask.settingsObj.Advanced_smooth_offset
      else:
          smooth_offset = eval(self.monitask.settingsObj.Advanced_smooth_offset) if type(self.monitask.settingsObj.Advanced_smooth_offset)==str else 0.25


      if type(self.monitask.settingsObj.Advanced_smooth_minDist) == int:
          smooth_minDist = self.monitask.settingsObj.Advanced_smooth_minDist
      else:
          smooth_minDist = eval(self.monitask.settingsObj.Advanced_smooth_minDist) if type(self.monitask.settingsObj.Advanced_smooth_minDist) == str else 0

      if type(self.monitask.settingsObj.Advanced_smooth_maxAngle) == int:
          smooth_maxAngle = self.monitask.settingsObj.Advanced_smooth_maxAngle
      else:
          smooth_maxAngle = eval(self.monitask.settingsObj.Advanced_smooth_maxAngle) if type(self.monitask.settingsObj.Advanced_smooth_maxAngle) == str else 180

      def simplifyPreserveTopology(geometry):
          #global simplify_torlerance
          if type(geometry)== ogr.Geometry:
              ogr_geometry=geometry.SimplifyPreserveTopology(simplify_torlerance * self.working_resolution)
              return QgsGeometry.fromWkt(ogr_geometry.ExportToWkt())
          elif type(geometry)== QgsGeometry:
              ogr_geometry=ogr.CreateGeometryFromWkt(geometry.asWkt())
              ogr_geometry = ogr_geometry.SimplifyPreserveTopology(simplify_torlerance * self.working_resolution)
              return QgsGeometry.fromWkt(ogr_geometry.ExportToWkt())
      def simplify(qgs_geometry):
          #global simplify_torlerance
          return qgs_geometry.simplify(simplify_torlerance*self.working_resolution)
      def orthogonalize(qgs_geometry):
          #global ortho_torlerance,ortho_angleThreshold
          return qgs_geometry.orthogonalize(tolerance=ortho_torlerance, maxIterations=1000, angleThreshold=ortho_angleThreshold)
      def smooth(qgs_geometry):
          #global smooth_iterations,smooth_offset,smooth_minDist,smooth_maxAngle
          return qgs_geometry.smooth(iterations=smooth_iterations,
                                     offset=smooth_offset,
                                     minimumDistance=smooth_minDist*self.working_resolution,
                                     maxAngle=smooth_maxAngle)
      def snapToGrid(qgs_geometry):
          #global snap2grid_hspace,snap2grid_vspace
          return qgs_geometry.snappedToGrid(snap2grid_hspace,snap2grid_vspace)

      func_dict={"SimplifyPreserveTopology":simplifyPreserveTopology,
                 "Simplify":simplify,
                 "Orthogonalize":orthogonalize,
                 "Smooth":smooth,
                 "SnapToGrid":snapToGrid,
                 "default":simplifyPreserveTopology
                 }

      qgs_fields =[QgsField('value', QVariant.Int)]
      qgs_layer = QgsVectorLayer('Polygon?crs='+self.monitask.wl.crs.authid(), 'temp_parcel', 'memory')
      qgs_layer.startEditing()
      for qgs_field in qgs_fields:
          qgs_layer.addAttribute(qgs_field)
      qgs_layer.commitChanges()

      # 遍历OGR图层
      features=[]
      i=0
      for ogr_feature in ogr_Layer:
          i+=1
          #print_log(i,ogr_feature.GetField('value'),ogr_feature.GetGeometryRef().GetArea())
          if ogr_feature.GetField('value')==0:
              continue
          # 获取要素几何体
          ogr_geometry = ogr_feature.GetGeometryRef()
          #在这里或调用该函数的位置之后判断并获取Label
          geometry=QgsGeometry.fromWkt(ogr_geometry.ExportToWkt())

          # 进行简化和平滑处理，次布宜在确定类型后，根据类型特点，根据需要进行简化或平滑一种或两种组合处理
          #print_log(labelObj.reshape_rule)
          if labelObj and labelObj.reshape_rule:
              if type(labelObj.reshape_rule)==list:
                  if len(labelObj.reshape_rule)<1:
                      geometry = func_dict["default"](geometry)
                  else:
                      for method in labelObj.reshape_rule:
                          geometry=func_dict[method](geometry)

          geometry.removeDuplicateNodes()
          #print_log("maptool:is multipart?",geometry.isMultipart())
          if geometry.isMultipart():
              #print_log("maptool: convert_ogrLayer2qgsLayer: The polygon from ogr layer is a multipart polygon after reshaped")
              for part in geometry.asGeometryCollection():
                  if part.area()>=area_limit:
                      feat = QgsFeature(qgs_layer.fields())
                      feat.setAttribute('value', ogr_feature.GetField('value'))
                      feat.setGeometry(part)
                      features.append(feat)
          else:
              feat = QgsFeature(qgs_layer.fields())
              feat.setAttribute('value', ogr_feature.GetField('value'))
              feat.setGeometry(geometry)
              features.append(feat)

      qgs_layer.dataProvider().addFeatures(features)
      qgs_layer.updateExtents()
      return qgs_layer

      #QgsProject.instance().addMapLayer(qgs_layer)
  def copyFeaturesTo(self,srcLayer,targetLayer,minArea=200):
      #如果snapping设置只能对每次paste一个起作用：
      #srcLayer.setFlags(QgsMapLayer.Private)
      QgsProject.instance().addMapLayer(srcLayer)
      # features = srcLayer.getFeatures()
      # for feature in features:
      #     QMessageBox.about(None, 'Notice', str(feature.id())+"-to-"+targetLayer.name())
      #     self.iface.setActiveLayer(srcLayer)
      #     srcLayer.selectByIds([feature.id()])
      #     # Copy
      #     self.iface.actionCopyFeatures().trigger()
      #     # Set destination layer active
      #     self.iface.setActiveLayer(targetLayer)
      #     # Turn on editing on destination layer, so we can paste
      #     targetLayer.startEditing()
      #     # Paste features
      #     self.iface.actionPasteFeatures().trigger()
      #否则，一次全拷并完成paste
      self.iface.setActiveLayer(srcLayer)
      srcLayer.selectByExpression("area($geometry)>{}".format(minArea))
      #srcLayer.selectAll()
      self.iface.actionCopyFeatures().trigger()
      # Set destination layer active
      self.iface.setActiveLayer(targetLayer)
      # Turn on editing on destination layer, so we can paste
      targetLayer.startEditing()
      # Paste features
      self.iface.actionPasteFeatures().trigger()
      targetLayer.commitChanges()
      QgsProject.instance().removeMapLayer(srcLayer.id())

  def undo(self):
      '''
      todo: 将最近加入的样点删除，重新调用do_seg生成mask
      '''
      if len(self.click_points)>0:
          self.click_points.pop()
          self.click_points_mode.pop()
          if len(self.click_points)==0:
              if  self.temp_mask_layer:
                  QgsProject.instance().layerTreeRoot().findLayer(self.temp_mask_layer.id()).setItemVisibilityChecked(False)
          else:
              self.do_seg()

  def cancel(self):
      '''
      todo: 中断采样，清除样点和已生成的mask
      '''
      self.click_points.clear()
      self.click_points_mode.clear()
      self.extending_labelid=-1
      self.masks=None
      try:
          if self.temp_mask_layer:
              tmplyr=QgsProject.instance().layerTreeRoot().findLayer(self.temp_mask_layer.id())
              if tmplyr:
                  tmplyr.setItemVisibilityChecked(False)
      except:
          pass

  def max_square4bi_matrix(self,matrix):
      """
      给出了一个 m x n 的矩阵 matrix ，里面每个格子填充了 0 或者 1 ，找到只包含 1 的最大的正方形面积并返回,
      DP (bottom-up) approach
      参考：https://www.techgeekbuzz.com/blog/maximum-size-square-sub-matrices-with-all-1s/
      :matrix: 0或1组成的二值图
      :return 最大正方形的右下角位置索引(row,col）和正方形的边长
      """
      M = len(matrix)
      N = len(matrix[0])
      #print_log("mask size:{}*{}".format(M,N))
      dp = np.zeros((M, N)).astype("uint8")
      for n in range(N):
          dp[0][n] = int(matrix[0][n])
      for m in range(M):
          dp[m][0] = int(matrix[m][0])
      for i in range(1, M):
          for j in range(1, N):
              if matrix[i][j] == 0:
                  continue
              dp[i][j] = min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]) + 1
      ind = np.unravel_index(np.argmax(dp, axis=None), dp.shape)
      #print_log(ind, dp[ind])
      return ind, dp[ind]

  def clip_img_by_mask(self):
      parcel_image=cv2.bitwise_and(self.workingImg,self.workingImg,mask=self.masks)
      contoures,_=cv2.findContours(self.masks,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
      max_area=0
      index=-1
      for i in range(len(contoures)):
          if contoures[i].size>max_area:
              max_area=contoures[i].size
              index=i
      x,y,w,h=cv2.boundingRect(contoures[index])
      parcel_image=parcel_image[y:y+h,x:x+w]

      right_bottom,edge_len=self.max_square4bi_matrix(self.masks[y:y+h,x:x+w])
      samp_image=parcel_image[right_bottom[0]-edge_len+1:right_bottom[0]+1,right_bottom[1]-edge_len+1:right_bottom[1]+1]

      # cv2.imshow("croped image",parcel_image)
      # cv2.imshow("sample image",samp_image)
      # cv2.waitKey(0)
      # cv2.destroyAllWindows()
      return parcel_image,samp_image

  def canvasMovedAgain_ByPan(self,distance,unit,bearing):
      pass
      #print(distance,unit,bearing)
      #self.CD_InProcessing=True

  def canvasMovedAgain_ByScale(self,value):
      pass
      #print(value)
      #self.CD_InProcessing=True

  def detect_changes(self,window_size=(224,224)):
      '''
      基于计算embbeding之间的相似性来判断两期影像之间的变化情况，基本步骤：
      1、提取覆盖当前窗口的两期影像
      2.1、分块判断是否已经检测过，将未检测过的块筛选出来，并分块判断信息量变化，对变化较大的进行直方图匹配，消除色调差异
      2.2、同时转换一对灰度图像，也做3、4步，有可能能够排除由于季节差异导致的未变化，但经过实验，未能形成结论，故暂时不做已节约响应时间
      2.3、TODO：有必要采用匹配算法进行几何位置对齐，消除由于影像位置精度造成的影响，但这样需要扩展块的大小。
      3、将未检测过的块组织成批，送入encoder生成embbedings
      4、计算相似性，并输出结果
      '''
      # import time
      # import cv2,random
      def has_detected(row,col,L):
          '''
          通过查询的方式确定当前块是否已经检测过
          '''
          self.monitask.wl.changedetected_layer.selectByExpression('"cell_level" = \'{}\' and "cell_row" = \'{}\' and "cell_col" = \'{}\''.format(L,row,col),
                                                                   QgsVectorLayer.SetSelection)
          feats = self.monitask.wl.changedetected_layer.selectedFeatures()
          return len(feats)>0

      def not_detected(row_range,col_range,L):
          '''
          通过查询的方式确定指定范围内未检测过的行列号
          '''
          all=[]
          for col in range(col_range[0],col_range[1]+1):
              all.extend(list(zip([L]*(row_range[1]-row_range[0]+1),range(row_range[0],row_range[1]+1),[col]*(row_range[1]-row_range[0]+1))))
          self.monitask.wl.changedetected_layer.selectByExpression('"cell_level" = \'{}\' and "cell_row" >= \'{}\' and "cell_row" <= \'{}\' and "cell_col" >= \'{}\' and "cell_col" <= \'{}\''.format(L,
                                                                                                                                                                                                    row_range[0],row_range[1],
                                                                                                                                                                                                    col_range[0],col_range[1]),
                                                                   QgsVectorLayer.SetSelection)
          feats = self.monitask.wl.changedetected_layer.selectedFeatures()
          detected=[]
          for feat in feats:
              detected.append((feat["cell_level"],feat["cell_row"],feat["cell_col"]))
          self.monitask.wl.changedetected_layer.removeSelection()
          result=set(all)-set(detected)
          return list(result)

      def detect_change_by_embedding(c_img1,c_img2,embedding1,embedding2,row,col,L):
          feat = QgsFeature(self.monitask.wl.changedetected_layer.fields())
          feat.setAttribute("cell_level", L)
          feat.setAttribute("cell_row", row)
          feat.setAttribute("cell_col", col)
          feat.setAttribute("working_img", self.monitask.wl.baseimg_layer.name())
          feat.setAttribute("prev_img", self.monitask.wl.previmg_layer.name())
          feat.setAttribute("working_resolution", L * 0.2)
          box = QgsRectangle((col - 1) * c_img1.shape[0] * L * 0.2,
                             (row - 1) * c_img1.shape[1] * L * 0.2,
                             col * c_img1.shape[0] * L * 0.2,
                             row * c_img1.shape[1] * L * 0.2)
          csim = cosine_similarity(embedding1, embedding2)
          cmutinfo = mutual_info(c_img1, c_img2)
          chissim = cosine_similarity(rgb_histogram(c_img1), rgb_histogram(c_img2))
          feat.setAttribute("csim", csim)
          feat.setAttribute("cmutinfo", float(cmutinfo))
          feat.setAttribute("chissim", chissim)
          # g_img1 = cv2.cvtColor(c_img1, cv2.COLOR_BGR2GRAY)
          # g_img2 = cv2.cvtColor(c_img2, cv2.COLOR_BGR2GRAY)
          # gsim = cosine_similarity(embedding1, embedding2)
          # gmutinfo = mutual_info(g_img1, g_img2)
          # ghissim = cosine_similarity(rgb_histogram(g_img1), rgb_histogram(g_img2))
          # feat.setAttribute("gsim", gsim)
          # feat.setAttribute("gmutinfo", float(gmutinfo))
          # feat.setAttribute("ghissim", ghissim)
          feat.setGeometry(QgsGeometry.fromRect(box))
          return feat

      if self.CD_InProcessing:
          return
      else:
          self.CD_InProcessing=True
      #start=time.time()
      print("***************************Extent Changed****************************")
      self.canvas.refresh()
      canv_ext=self.canvas.extent()
      #根据当前显示分辨率进行变化监测
      #L=math.ceil(self.get_display_resolution()/0.2)
      # 根据当前分割使用的分辨率进行变化监测更可靠
      L=math.ceil(self.working_resolution/0.2)
      L_resolution=L*0.2
      col_range=(math.floor(canv_ext.xMinimum() / L_resolution / window_size[0]),
                 math.ceil(canv_ext.xMaximum() / L_resolution / window_size[0]))
      row_range=(math.floor(canv_ext.yMinimum() / L_resolution / window_size[1]),
                 math.ceil(canv_ext.yMaximum() / L_resolution / window_size[1]))
      L_ext=QgsRectangle((col_range[0]-1)*window_size[0]*L_resolution,
                        (row_range[0]-1) * window_size[1] * L_resolution,
                        col_range[1]  * window_size[0] * L_resolution,
                        row_range[1]  * window_size[1] * L_resolution)
      c_img1 = self.cutoutImageFromRasterLayer(self.monitask.wl.previmg_layer, L_ext,
                                               window_size[0]*(col_range[1]-col_range[0]+1),
                                               window_size[1]*(row_range[1]-row_range[0]+1))
      c_img2 = self.cutoutImageFromRasterLayer(self.monitask.wl.baseimg_layer, L_ext,
                                               window_size[0]*(col_range[1]-col_range[0]+1),
                                               window_size[1]*(row_range[1]-row_range[0]+1))
      #cv2.imshow("img1",c_img1)
      features=[]
      i=0
      # rows=list(range(row_range[0], row_range[1] + 1))
      # cols=list(range(col_range[0], col_range[1] + 1))
      # random.shuffle(rows)
      # random.shuffle(cols)
      tiles_idx=[]
      tiles_img=[]
      to_detect=not_detected(row_range,col_range,L)
      msg="Preparing Detect Changes for {} blocks at level {}...".format(len(to_detect),L)
      for cell in to_detect:
          i += 1
          print(msg + str(i))
          QApplication.processEvents()
          self.iface.mainWindow().statusBar().showMessage(msg + str(i))
          tc_img1 = c_img1[(cell[1] - row_range[0]) * window_size[1]:(cell[1] - row_range[0] + 1) * window_size[1],
                    (cell[2] - col_range[0]) * window_size[0]:(cell[2] - col_range[0] + 1) * window_size[0], :]
          tc_img2 = c_img2[(cell[1] - row_range[0]) * window_size[1]:(cell[1] - row_range[0] + 1) * window_size[1],
                    (cell[2] - col_range[0]) * window_size[0]:(cell[2] - col_range[0] + 1) * window_size[0], :]
          # cv2.imshow("timg1", tc_img1)
          if tc_img1 is not None and tc_img2 is not None:
              # 两个时相的信息量基本相同时，不做色彩匹配，否则需要做色彩匹配。
              # 理想状态，如果信息量相同，长而不再进行变化检测，直接认为无变化，目前未考虑
              entro1 = get_entropy(tc_img1)
              entro2 = get_entropy(tc_img2)
              if abs(entro1 - entro2) > 3:
                  if entro1 - entro2 > 3:
                      infer_map = get_infer_map(tc_img1)  # 计算参考映射关系
                      tc_img2 = get_new_img(tc_img2, infer_map)  # 根据映射关系获得新的图像
                  elif entro2 - entro1 > 3:
                      infer_map = get_infer_map(tc_img2)  # 计算参考映射关系
                      tc_img1 = get_new_img(tc_img1, infer_map)  # 根据映射关系获得新的图像
              tiles_idx.append((cell[1], cell[2]))
              tiles_img.append((tc_img1, tc_img2))
          # if the canvas changed during the processing, stop here
          #if self.CD_InProcessing: return

      batch_size=30
      total=len(tiles_idx)
      iter=math.ceil(total*1.0/batch_size)
      tiles_img=np.array(tiles_img)
      #print("All tiles:",tiles_img.shape)
      done=0
      msg="Detecting Changes for {} blocks at level {}...".format(total,L)
      for batch in range(iter):
          s=batch*batch_size
          e=(batch+1)*batch_size
          tc_embbedings1=self.monitask.encoder.get_embeddings_in_batch(tiles_img[s:e,0])
          tc_embbedings2=self.monitask.encoder.get_embeddings_in_batch(tiles_img[s:e,1])
          for i in range(batch_size):
              if done>=total: break
              #print("Row,Col:",tiles_idx[done][0], tiles_idx[done][1])
              print(msg + str(done), self.CD_InProcessing)
              #QApplication.processEvents()
              self.iface.mainWindow().statusBar().showMessage(msg + str(done))
              feature = detect_change_by_embedding(tiles_img[done][0],tiles_img[done][1],
                                                   tc_embbedings1[i],   tc_embbedings2[i],
                                                   tiles_idx[done][0], tiles_idx[done][1], L)
              features.append(feature)
              done=done+1
              # if the canvas changed during the processing, skip the rest and commit the got features
              #if self.CD_InProcessing: break
              #break
          #if self.CD_InProcessing: break
          #break
      #self.iface.mainWindow().statusBar().clearMessage()
      if len(features)>0:
          self.monitask.wl.changedetected_layer.dataProvider().addFeatures(features)
          print("Features added:",len(features))
          self.monitask.wl.changedetected_layer.updateExtents()
          print("updateExtents")
          #self.canvas.freeze(False)
          self.monitask.wl.changedetected_layer.reload()
          print("layer.reload")
          self.canvas.refresh()
          print("canvas.refresh")
      self.CD_InProcessing=False
      #print("Time2:",time.time()-start)

class MaskCanvasItem(QgsMapCanvasItem):
  def __init__(self, canvas):
    super().__init__(canvas)
    self.center = QgsPoint(0, 0)
    self.size   = 100

  def setCenter(self, center):
    self.center = center

  def center(self):
    return self.center

  def setSize(self, size):
    self.size = size

  def setMask(self,mask_data):
    self.mask=mask_data


  def size(self):
    return self.size

  def boundingRect(self):
    return QRectF(self.center.x() - self.size/2, self.center.y() - self.size/2,self.size,self.size)

  def paint(self, painter, option, widget):
    painter.setPen(QPen(Qt.green, 8, Qt.DashLine))
    # path = QPainterPath()
    # path.moveTo(self.center.x(), self.center.y());
    # path.arcTo(self.boundingRect(), 0.0, 360.0)
    # painter.fillPath(path, QColor("red"))

    painter.drawEllipse(int(self.center.x()), int(self.center.y()), 50, 50)

    painter.drawRect(self.boundingRect())
    #QgsMessageLog.logMessage(self.boundingRect().toString(), level=Qgis.Info)
    painter.setPen(QPen(Qt.red, 8, Qt.DashLine))
    painter.drawRect(int(self.center.x()-self.size/2), int(self.center.y()-self.size/2),self.size,self.size)

    # if self.mask:
    #     color = np.array([0, 0, 255])
    #     h, w = self.mask.shape[-2:]
    #     mask_image = self.mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    #     mask_image = mask_image.astype("uint8")
    #     mask_image = cv2.cvtColor(mask_image, cv2.COLOR_BGR2RGB)
    #     #mask_image = cv2.addWeighted(self.image_data, 0.5, mask_image, 0.9, 0)
    #     mask_image = QImage(mask_image[:], mask_image.shape[1], mask_image.shape[0], mask_image.shape[1] * 3,
    #                               QImage.Format_RGB888)
    #     mask_pixmap = QPixmap(mask_image)
    #     # self.mask_item.setPixmap(mask_pixmap)
    #     # pic = QPixmap("Shape_1.png")
    #     painter.drawPixmap(self.boundingRect(), mask_pixmap)


def testClipboard():
    '''
    1 Select features in source_layer.
    2 Use iface.copySelectionToClipboard(source_layer)
    3 Open the edit session in target_layer.
    4 Use iface.pasteFromClipboard(target_layer)
    5 Save changes to target_layer.
    '''
    # Destination Layer...
    CapaDestino = QgsProject.instance().mapLayersByName("Predios Lineas")[0]

    # Dialog Box for input "ID del Predio" to select it...
    ID_Predio = QInputDialog.getText(None, 'ID del Predio', 'Input ID del Predio')
    Predio = int(ID_Predio[0])  # String to Number

    # select the polygons to copy from...
    CapaOrigen.selectByExpression('"ID_Predio" = {}'.format(Predio), QgsVectorLayer.SetSelection)
    #或者
    CapaOrigen.selectAll()


    # Store selected polygons in a list....
    # to know the numbers of selected polygons...
    Pol_seleccionados = CapaOrigen.selectedFeatures()
    print_log("Número de polígonos seleccionados: ", len(Pol_seleccionados))

    # Detect if there are selected polygons...
    if len(Pol_seleccionados) == 0:
        print_log("==================================================")
        print_log("NO hay polígonos para el Predio ", Predio, "... Check.")
        print_log("               FIN DEL PROCESO")
        print_log("==================================================")
    else:
        # ===========================================================
        # Copy the selected polygons
        iface.actionCopyFeatures().trigger()

        # Change and Activate the Destine Layer
        iface.setActiveLayer(CapaDestino)

        # Put the Destine Layer in Edition
        CapaDestino.startEditing()

        # Paste the selected polygons
        iface.actionPasteFeatures().trigger()

        # Zoom to selected...
        iface.mapCanvas().zoomToSelected()

        # Save
        CapaDestino.commitChanges()
        print_log("==================================================")
        print_log("Capa actualizada con el Predio ", Predio)
        print_log("               PROCESO EXITOSO")
        print_log("==================================================")


