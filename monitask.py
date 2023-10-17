# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Monitask
                                 A QGIS plugin
 遥感监测作业插件
                              -------------------
        begin                : 2022-04-23
        git sha              : $Format:%H$
        copyright            : (C) 2022 by zhouxu/NGCC
        email                : zhouxu@ngcc.cn
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import  QTranslator, QCoreApplication, Qt, QObject
from qgis.PyQt.QtGui import QIcon,QFont,QColor
from qgis.PyQt.QtWidgets import QAction,QMenu,QMessageBox, QWidget,QHBoxLayout,QWidgetAction,QActionGroup,QSpinBox,QComboBox
from qgis.core import (Qgis,QgsIdentifyContext,QgsProject,QgsSnappingConfig, QgsLayerTreeGroup,
                       QgsMapThemeCollection, QgsMessageLog,QgsFeatureRequest,QgsSymbol,QgsSimpleFillSymbolLayer,
                       QgsSymbolLayer,QgsProperty, QgsSingleSymbolRenderer,QgsTextFormat,QgsPalLayerSettings,
                       QgsVectorLayerSimpleLabeling)
from qgis.gui  import QgsGui,QgsMapToolIdentify,QgsOptionsWidgetFactory, QgsOptionsPageWidget,QgsHighlight

# Initialize Qt resources from file resources.py
from .resources import *

import os.path
from datetime import datetime


from .settings_dialog import *
from .labeleditor import *
from .labelchecker import *
from .task_dialog import *
from .maptool import *
from .sam.segment_any import SegAny
from .encode_worker import EncodeWorker

#from .sam.gpu_resource import GPUResource_Thread, osplatform
from .settings import SettingsClass
from .working_layers import WorkingLayers
from .labelbase import *
from .utils import getFieldSources,print_log,newDetectedChangesLayer
import logging


class MonitaskOptionsFactory(QgsOptionsWidgetFactory):

    def __init__(self):
        super().__init__()

    def icon(self):
        return QIcon(':/plugins/monitask/monitask.svg')

    def createWidget(self, parent):
        return ConfigOptionsPage(parent)


class ConfigOptionsPage(QgsOptionsPageWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        #self.labelWidget = LabelEditor()
        self.settingsDlg = SettingsDialog()
        icon_path = ':/plugins/monitask/icon.png'
        icon = QIcon(icon_path)
        self.settingsDlg.setWindowIcon(icon)
        layout.addWidget(self.settingsDlg)
        #layout.addWidget(self.labelWidget)

        self.setLayout(layout)
    def apply(self):
        #Todo: 在这里进行保存设置结果等处理
        pass


class Monitask:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.seg_status=False
        self.sam_enabled=False
        self.segany=None
        self.encoder=None
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize plugin related layers
        self.layers=[]
        self.actions=[]
        configPath=os.path.dirname(__file__) + "\\monitask_config.ini"
        self.configInitiated=os.path.exists(configPath)
        self.settingsObj=SettingsClass(configPath, SettingsClass.IniFormat)
        self.settingsDlg=SettingsDialog(settingsObj=self.settingsObj)
        self.segtool=SegMapTool(self)
        self.checktool=LabelCheckTool(self)
        self.labelWidget=LabelEditor(self)
        self.labelCheckWidget=LabelChecker(self)
        self.wl = WorkingLayers()
        self.lb=LabelBase(self.settingsObj.General_labelDBFile)
        self.navitool_initiated=False
        self.canvasItem_Focus=None

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Monitask_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)
        self.config_logger()

    def config_logger(self):
        #print("config_logger。。。")
        logger = logging.getLogger("Monitask")
        logger.setLevel(level=logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        if len(logger.handlers)<1:
            logger.addHandler(console)
        else:
            logger.removeHandler(logger.handlers[0])
            logger.addHandler(console)
        logger.propagate = False

    def tr(self, message):
        """Get the translation for a string using Qt translation API.
        We implement this ourselves since we do not inherit QObject.
        :param message: String for translation.
        :type message: str, QString
        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Monitask', message)

    def create_action(self,parentObj,
                      icon_path,
                      action_objName,
                      action_title,
                      action_whatsthis,
                      action_tip,
                      triggered_func,
                      shortcut=None):
        new_action = QAction(self.tr(action_title),self.iface.mainWindow())
        icon = QIcon()
        icon.addPixmap(QtGui.QPixmap(icon_path), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        new_action.setIcon(icon)
        new_action.setObjectName(action_objName)
        #new_action.setText(self.tr(action_title))
        new_action.setWhatsThis(self.tr(action_whatsthis))
        new_action.setStatusTip(self.tr(action_tip))
        if shortcut is not None:
            self.iface.registerMainWindowAction(new_action, shortcut)
        if parentObj:
            parentObj.addAction(new_action)
        new_action.triggered.connect(triggered_func)
        #QgsGui.shortcutsManager().registerAction(new_action,shortcut)
        self.actions.append(new_action)
        return new_action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        title = self.iface.mainWindow().windowTitle()
        new_title = title.replace('QGIS', 'Monitask')
        self.iface.mainWindow().setWindowTitle(new_title)

        icon_path = ':/plugins/monitask/monitask.svg'
        icon = QIcon(icon_path)
        self.iface.mainWindow().setWindowIcon(icon)
        self.labelWidget.setFocusPolicy(Qt.StrongFocus)

        self.options_factory = MonitaskOptionsFactory()
        self.options_factory.setTitle(self.tr('Monitask'))
        self.options_factory.setIcon(icon)
        self.iface.registerOptionsWidgetFactory(self.options_factory)

        self.monitask_menu = QMenu(self.tr(u'&Monitask'))
        self.iface.mainWindow().menuBar().insertMenu(self.iface.firstRightStandardMenu().menuAction(),
                                                     self.monitask_menu)
        
        self.task_action=self.create_action(self.monitask_menu,':/plugins/monitask/get_task.svg',
                                            "taskAction","Get Task","browse tasks","This is task tip",self.showTaskDialog,shortcut="Alt+T")

        self.submit_action=self.create_action(self.monitask_menu,':/plugins/monitask/submit_task.svg',
                                              "submitAction","Submit Task","submit task","This is task tip",self.submit,shortcut="Alt+S")

        self.settings_action=self.create_action(self.monitask_menu,':/plugins/monitask/settings.svg',
                                              "settingsAction","Settings","settings dialog","open the settings dialog",self.showSettingsDlg,shortcut="Alt+G")

        self.bimapview_action=self.create_action(self.monitask_menu,':/plugins/monitask/settings.svg',
                                              "bimapviewAction","Two Mapview Mode","show two mirror map windows","show two mirror map windows",self.showPreimgInOtherView,shortcut="Alt+B")

        # self.labels_action=self.create_action(self.monitask_menu,':/plugins/monitask/label.svg',
        #                                       "labelAction","&Labels","label panel","open the label edit panel",self.showLabelWidget,shortcut="Alt+L")
        self.segstatus_action=self.create_action(self.monitask_menu,':/plugins/monitask/segment.svg',
                                              "segstatusAction","Segmentation","Switch into segment status","Switch into segment status",self.switch_segstatus,shortcut="Q")

        self.segstatus_action.setCheckable(True)


        self.monitask_toolbar=self.iface.addToolBar('Monitask')
        self.monitask_toolbar.addAction(self.segstatus_action)
        #add extending_mode_combobox
        # self.extending_mode_combo = QComboBox()
        # self.extending_mode_combo.addItems(["Manual","Interactive","Auto"])
        # self.extending_mode_combo.setToolTip("Set the extending mode")
        # self.extending_mode_combo.setCurrentIndex(0)
        # self.monitask_toolbar.addWidget(self.extending_mode_combo)

        self.segfinish_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/finished.svg',
                                              "segfinishAction","Finish Segment","segment finished","segment finished",self.seg_finished,shortcut="E")
        self.segcancel_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/cancel.svg',
                                              "segcancelAction","Cancel Segment","segment canceled","segment canceled",self.seg_canceled,shortcut="ESC")
        self.segundo_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/undo.svg',
                                              "segundoAction","Undo Segment","segment backspace","segment backspace",self.seg_undo,shortcut="C")
        self.dilatemask_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/expand.svg',
                                              "dilatemaskAction","Dilate Mask","Adjust the mask-dilate","Adjust the mask-dilate",self.dilate_mask,shortcut="1")
        self.erodemask_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/shrink.svg',
                                              "erodemaskAction","Erode Mask","Adjust the mask-erode","Adjust the mask-erode",self.erode_mask,shortcut="2")

        if self.settingsObj.General_pos_index_source is not None:
            self.wl.setNaviLayer(QgsVectorLayer(self.settingsObj.General_pos_index_source, "NaviLayer", "ogr"))

        if hasattr(self.wl, "navi_layer") and self.wl.navi_layer is not None and self.wl.navi_layer.isValid():
            fid_min,fid_max=self.wl.navi_layer.minimumAndMaximumValue(0)
            if fid_min:
                self.monitask_toolbar.addSeparator()
                self.navi_action = self.create_action(self.monitask_toolbar, ':/plugins/monitask/navi.svg',
                                                      "naviAction", "navigate to targets", "navigate to targets",
                                                      "navigate to targets", self.navigateTo, shortcut="N")
                self.navi_index_spin = QSpinBox()
                self.navi_index_spin.setToolTip("{} - {}".format(fid_min,fid_max))
                self.navi_index_spin.setRange(fid_min,fid_max)
                self.monitask_toolbar.addWidget(self.navi_index_spin)
                self.navitool_initiated=True

        self.monitask_toolbar.addSeparator()
        self.identify_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/mining.svg',
                                              "identityAction","Extract attribute values from sources","Extract attribute values from sources","Extract attribute values from sources",self.identify,shortcut="X")
        self.monitask_toolbar.addSeparator()
        self.labelcheck_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/label_check.svg',
                                              "labelcheckAction","check the label samples","check the label samples","check the label samples",self.labelCheck,shortcut="V")
        self.labelcheck_action.setCheckable(True)
        self.labelcheck_action.setDisabled(True)


        self.changedetect_action=self.create_action(self.monitask_toolbar,':/plugins/monitask/change_detect.svg',
                                              "changedetectAction","enable change detection","enable change detection","enable change detection",self.test_change_detect,shortcut="D")
        self.changedetect_action.setCheckable(True)
        self.changedetect_action.setDisabled(True)

        self.monitask_toolbar.addSeparator()
        self.monitask_toolbar.addAction(self.settings_action)

        #todo the next work to be extended
        # self.monitask_toolbar.addSeparator()
        # self.monitask_toolbar.addAction(self.task_action)
        # self.monitask_toolbar.addAction(self.submit_action)

        self.gridstatus_action2=self.create_action(None,':/plugins/monitask/done.svg',
                                              "gridstatus_finished","-> &Done","tag the grid as finished","tag the grid as finished",self.setgridstatus_finished)

        self.gridstatus_action1=self.create_action(None,':/plugins/monitask/doing.svg',
                                              "gridstatus_tobecontinue","-> Do&ing","tag the grid as doing","tag the grid as doing",self.setgridstatus_tobecontinue)

        self.gridstatus_action0=self.create_action(None,':/plugins/monitask/todo.svg',
                                              "gridstatus_waittostart","-> &To do","tag the grid as todo","tag the grid as todo",self.setgridstatus_waittostart)

        self.iface.mapCanvas().contextMenuAboutToShow.connect(self.showCanvasContextMenu)

        QgsProject.instance().snappingConfigChanged.connect(self.setDefaultSnappingConfig)
        QgsProject.instance().topologicalEditingChanged.connect(self.setDefaultSnappingConfig)
        QgsProject.instance().avoidIntersectionsModeChanged.connect(self.setDefaultSnappingConfig)
        QgsProject.instance().writeProject.connect(self.onProjectSaving)
        QgsProject.instance().projectSaved.connect(self.onProjectSaveAndClosed)
        QgsProject.instance().dirtySet.connect(self.onProjectDirtySet)

        self.segstatus_action.changed.connect(self.segTool_toggled)
        self.labelcheck_action.changed.connect(self.checkTool_toggled)

        #暂时关闭下面一行
        #self.configChangeLayerSlot()

        self.initSAM()
        self.segtool.segany = self.segany
        self.init_encoder()
        self.grouping_actions()
        self.disableTools(True)
        while not self.configInitiated:
            self.showSettingsDlg()
            self.settingsDlg.accEdt.setFocus()
            configPath=os.path.dirname(__file__) + "\\monitask_config.ini"
            self.configInitiated=os.path.exists(configPath)
            if not self.configInitiated:
                QMessageBox.warning(None, 'Warning','You must set basic information for Monitask to work , including username, working directory, working result output file and label system database etc.\n必需设置用户名、工作目录、工作成果保存文件相关信息以及标签库等基本信息，并确认保存。')

    def identify(self,overwrite=True):
        try:
            if self.wl.output_layer:
                if isOutputLayerValid(self.wl.output_layer,self.settingsObj):
                    fieldSources=getFieldSources(self.wl.output_layer,self.settingsObj)
                    self.wl.output_layer.startEditing()
                    for fieldSrc in fieldSources:
                        print_log("Get values from {}.{} to fill my {}".format(fieldSrc[1],fieldSrc[2],fieldSrc[0]))
                        src_layer=QgsVectorLayer(fieldSrc[1])
                        if overwrite:
                            expression = 'fid >= 0'
                        else:
                            expression = fieldSrc[0]+" is NULL or "+fieldSrc[0]+" =''"
                        outlayer_request = QgsFeatureRequest().setFilterExpression(expression)
                        for feat in self.wl.output_layer.getFeatures(outlayer_request):
                            center = feat.geometry().centroid()
                            src_exp=fieldSrc[2] + " is not NULL and "+fieldSrc[2] +" !='' and contains($geometry,geom_from_wkt('" + center.asWkt() + "'))"
                            srclayer_request = QgsFeatureRequest().setFilterExpression(src_exp)
                            results = src_layer.getFeatures(srclayer_request)
                            for result in results:
                                self.wl.output_layer.changeAttributeValue(feat.id(),feat.fieldNameIndex(fieldSrc[0]),result[fieldSrc[2]])
                                #以下两行与上面一句等效
                                # feat.setAttribute(feat.fieldNameIndex(fieldSrc[0]),result[fieldSrc[2]])
                                # self.wl.output_layer.updateFeature(feat)
                                break
                    self.wl.output_layer.commitChanges()
        except Exception as e:
            print_log("Exception occured in monitask.identify:",e)

    def disableTools(self,disabled=True):
        self.segfinish_action.setDisabled(disabled)
        self.segcancel_action.setDisabled(disabled)
        self.segundo_action.setDisabled(disabled)
        self.dilatemask_action.setDisabled(disabled)
        self.erodemask_action.setDisabled(disabled)
        if self.navitool_initiated:
            self.navi_action.setDisabled(disabled)
        self.identify_action.setDisabled(disabled)
        # self.extending_mode_combo.setDisabled(disabled)

    def grouping_actions(self):
        '''
        把相关工具条中需要状态互斥的按钮加入到一个组中
        '''
        group=self.iface.mapToolActionGroup()
        group.addAction(self.segstatus_action)
        group.addAction(self.labelcheck_action)
        group.setExclusive(True)
        actionList = self.iface.mapNavToolToolBar().actions()
        for action in actionList:
            group.addAction(action)


    def unload(self):
        print_log("Unload Pluging .....")
        """Removes the plugin options settings."""
        self.iface.unregisterOptionsWidgetFactory(self.options_factory)

        """Removes the plugin menu item and icon from QGIS GUI."""
        if self.monitask_menu != None:
            self.iface.mainWindow().menuBar().removeAction(self.monitask_menu.menuAction())

        """Removes all actions from QGIS GUI."""
        for action in self.actions:
            self.iface.unregisterMainWindowAction(action)
            QgsGui.shortcutsManager().unregisterAction(action)
            self.iface.mainWindow().removeAction(action)

        if self.monitask_toolbar:
            del self.monitask_toolbar
        if self.segtool :
            self.segtool.seg_enabled = False
            self.segtool.clearCanvasItem()
            self.segtool.clearWorkLayers()
            del self.segtool
        if self.labelWidget:
            self.labelWidget.close()
            self.iface.removeDockWidget(self.labelWidget)
            del self.labelWidget
        if self.labelCheckWidget:
            self.labelCheckWidget.close()
            self.iface.removeDockWidget(self.labelCheckWidget)
            del self.labelCheckWidget
        if self.settingsDlg:
            self.settingsDlg.close()
            del self.settingsDlg
        if self.segany:
            self.segany.reset_image()
            self.segany.predictor=None
            del self.segany
        # if self.wl:
        #     del self.wl
        if self.canvasItem_Focus:
            self.iface.mapCanvas().scene().removeItem(self.canvasItem_Focus)
        for i in self.iface.mapCanvas().scene().items():
            if issubclass(type(i), QgsHighlight):
                self.iface.mapCanvas().scene().removeItem(i)
        self.iface.mapCanvas().refresh()

    def onProjectDirtySet(self):
        root = QgsProject.instance().layerTreeRoot()
        try:
            for child in root.children():
                if child.layer() is None:
                    root.removeChildNode(child)
        except:
            pass

    def onProjectSaving(self,anyvar):
        try:
            if self.seg_status:
                layerids = QgsProject.instance().mapLayers()
                for layerid in layerids:
                    layer = QgsProject.instance().mapLayer(layerid)
                    layer_name = layer.name()
                    if self.segtool.temp_mask_layer:
                        if self.segtool.temp_mask_layer.name()==layer_name:
                            print_log("Saving: ", layer_name)
                            self.segtool.temp_mask_layer=QgsProject.instance().takeMapLayer(layer)
                            QgsProject.instance().removeMapLayer(layerid)
                            continue
                    if self.segtool.working_extent_layer:
                        if self.segtool.working_extent_layer.name()==layer_name:
                            print_log("Saving: ", layer_name)
                            self.segtool.working_extent_layer=QgsProject.instance().takeMapLayer(layer)
                            QgsProject.instance().removeMapLayer(layerid)
                            continue
                    if QgsMapLayer.Private == layer.flags():
                        QgsProject.instance().removeMapLayer(layerid)
        except Exception as e:
            print_log("onProjectSaving:",e)

    def onProjectSaveAndClosed(self):
        #print_log("in onProjectSaveAndClosed......")
        try:
            if self.segtool:
                if self.segtool.temp_mask_layer:
                    self.segtool.temp_mask_layer.setFlags(QgsMapLayer.Private)
                    QgsProject.instance().addMapLayer(self.segtool.temp_mask_layer,True)
                    print_log("add existing temp_mask_layer",self.segtool.temp_mask_layer.id())
                if self.segtool.working_extent_layer:
                    self.segtool.working_extent_layer.setFlags(QgsMapLayer.Private)
                    QgsProject.instance().addMapLayer(self.segtool.working_extent_layer,True)
                    print_log("add existing working_extent_layer",self.segtool.working_extent_layer.id())
                #self.iface.mapCanvas().refresh()
        except Exception as e:
            #print_log("onProjectSaveAndClosed Exception:",e)
            pass

    def segTool_toggled(self):
        try:
            self.seg_status=self.segstatus_action.isChecked()
            if self.segtool:
                self.segtool.seg_enabled = self.seg_status
            if self.seg_status:
                print_log("segTool_toggled", self.seg_status)
                self.disableTools(False)
                self.showLabelWidget()
                self.iface.mapCanvas().setMapTool(self.segtool)
                if self.wl.output_layer:
                    self.labelcheck_action.setDisabled(False)
            else:
                self.disableTools(True)
                if self.labelWidget.isVisible():
                    #self.labelWidget.hide()
                    self.iface.removeDockWidget(self.labelWidget)
                self.iface.mapCanvas().layersChanged.disconnect()
                self.segtool.finish()
                self.segtool.cancel()
                self.segtool.clearCanvasItem()
                self.segtool.clearWorkLayers()
                self.iface.actionPan().trigger()
        except:
            pass

    def checkTool_toggled(self):
        try:
            if not self.labelcheck_action.isChecked():
                #print_log("checkTool_toggled", self.labelcheck_action.isChecked())
                if self.labelCheckWidget.isVisible():
                    self.labelCheckWidget.hide()
                if self.canvasItem_Focus:
                    self.iface.mapCanvas().scene().removeItem(self.canvasItem_Focus)
        except:
            pass

    def canvasLayersChanged(self):
        try:
            if self.labelWidget:
                if self.labelWidget.isVisible():
                    self.labelWidget.canvasLayersChanged()
        except Exception as e:
            #print_log("Exception 1 In monitask.canvasLayersChanged:",str(e))
            pass
        try:
            if not self.wl.isReady(self.settingsObj):
                # 通知segtool做同步
                self.seg_status = False
                self.segtool.seg_enabled = False
                self.iface.actionPan().trigger()
        except Exception as e:
            #print_log("Exception 2 In monitask.canvasLayersChanged:",str(e))
            pass

    def workingLayersChanged(self,baseimg_layer=None,output_layer=None,previmg_layer=None):
        if baseimg_layer is not None:
            self.wl.setBaseImageLayer(baseimg_layer)
        if previmg_layer is not None:
            self.wl.setPrevImageLayer(previmg_layer)
        if output_layer is not None:
            self.wl.setOutputLayer(output_layer)
        if baseimg_layer is not None:
            if self.segtool:
                self.segtool.cancel()
                self.segtool.refreshWorkingImage()

    # --------------------------------------------------------------------------
    def navigateTo(self):
        value=self.navi_index_spin.value()
        self.navi_index_spin.setValue(value+1)
        if hasattr(self.wl, "navi_layer") and self.wl.navi_layer is not None:
            feat=self.wl.navi_layer.getFeature(self.navi_index_spin.value())
            if feat.isValid():
                self.iface.mapCanvas().setCenter(feat.geometry().centroid().asPoint())
                self.iface.mapCanvas().refresh()

    def labelCheck(self):
        if self.labelcheck_action.isChecked():
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.labelCheckWidget)
            self.iface.mapCanvas().setMapTool(self.checktool)
            self.checktool.setCursor(Qt.PointingHandCursor)
            #self.iface.actionSelect().trigger()
        else:
            self.iface.removeDockWidget(self.labelCheckWidget)

    def switch_segstatus(self):
        #print_log(self.seg_status)
        #self.test_change_detect()
        pass
        # if self.segtool:
        #     self.segtool.seg_enabled = self.seg_status
        # if self.seg_status:
        #     self.showLabelWidget()
        #     self.iface.mapCanvas().setMapTool(self.segtool)
        #     if self.wl.output_layer:
        #         self.labelcheck_action.setDisabled(False)
        # else:
        #     self.iface.removeDockWidget(self.labelWidget)
        #     self.iface.mapCanvas().layersChanged.disconnect()
        #     self.segtool.finish()
        #     self.segtool.cancel()
        #     self.segtool.clearCanvasItem()
        #     self.segtool.clearWorkLayers()
        #     self.iface.actionPan().trigger()

    def showStatusMessage(self,message):
        QgsMessageLog.logMessage(message, level=Qgis.Info)
        #self.iface.statusBarIface().showMessage(message)
        #self.iface.messageBar().pushMessage("Ooops", message, level=Qgis.Info,duration=3)

    def initSAM(self):
        if os.path.exists(os.path.join(self.plugin_dir, 'weights/sam_hq_vit_tiny.pth')):
            # self.showStatusMessage('Find the checkpoint named {}.'.format('mobile_sam.pt'))
            self.segany = SegAny(os.path.join(self.plugin_dir, 'weights/sam_hq_vit_tiny.pth'))
            self.sam_enabled = True
        elif os.path.exists(os.path.join(self.plugin_dir,'weights/mobile_sam.pt')):
            #self.showStatusMessage('Find the checkpoint named {}.'.format('mobile_sam.pt'))
            self.segany = SegAny(os.path.join(self.plugin_dir,'weights/mobile_sam.pt'))
            self.sam_enabled = True
        elif os.path.exists(os.path.join(self.plugin_dir, 'weights/sam_hq_vit_h.pth')):
            # self.showStatusMessage('Find the checkpoint named {}.'.format('mobile_sam.pt'))
            self.segany = SegAny(os.path.join(self.plugin_dir, 'weights/sam_hq_vit_h.pth'))
            self.sam_enabled = True
        elif os.path.exists(os.path.join(self.plugin_dir,'weights/sam_vit_h_4b8939.pth')):
            #self.showStatusMessage('Find the checkpoint named {}.'.format('sam_vit_h_4b8939.pth'))
            self.segany = SegAny(os.path.join(self.plugin_dir,'weights/sam_vit_h_4b8939.pth'))
            self.sam_enabled = True
        elif os.path.exists(os.path.join(self.plugin_dir,'weights/sam_vit_l_0b3195.pth')):
            #self.showStatusMessage('Find the checkpoint named {}.'.format('sam_vit_l_0b3195.pth'))
            self.segany = SegAny(os.path.join(self.plugin_dir,'weights/sam_vit_l_0b3195.pth'))
            self.sam_enabled = True
        elif os.path.exists(os.path.join(self.plugin_dir,'weights/sam_vit_b_01ec64.pth')):
            #self.showStatusMessage('Find the checkpoint named {}.'.format('sam_vit_b_01ec64.pth'))
            self.segany = SegAny(os.path.join(self.plugin_dir,'weights/sam_vit_b_01ec64.pth'))
            self.sam_enabled = True
        else:
            QMessageBox.warning(None,'Warning','The checkpoint of [Segment anything] not existed. If you want use quick annotate, please download from {}'.format(
                                              'https://github.com/facebookresearch/segment-anything#model-checkpoints'))
            self.sam_enabled = False

    def init_encoder(self):
        if os.path.exists(os.path.join(self.plugin_dir,'weights/tiny_vit_5m_22k_distill.pth')):
            #self.showStatusMessage('Find the checkpoint named {}.'.format('weights/tiny_vit_5m_22k_distill.pth'))
            self.encoder = EncodeWorker(os.path.join(self.plugin_dir,'weights/tiny_vit_5m_22k_distill.pth'))
            self.encoder_enabled = True


    def seg_finished(self):
        try:
            self.iface.mapCanvas().layersChanged.disconnect(self.canvasLayersChanged)
        except Exception as e:
            print_log("Exception occured in monitask.seg_finished:",e)
        finally:
            if self.seg_status:
                self.segtool.finish()
            self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)

    def seg_canceled(self):
        try:
            self.iface.mapCanvas().layersChanged.disconnect(self.canvasLayersChanged)
        except Exception as e:
            print_log("Exception occured in monitask.seg_finished:",e)
        finally:
            if self.seg_status:
                self.segtool.cancel()
            self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)

    def seg_undo(self):
        try:
            self.iface.mapCanvas().layersChanged.disconnect(self.canvasLayersChanged)
        except Exception as e:
            print_log("Exception occured in monitask.seg_finished:",e)
        finally:
            if self.seg_status:
                self.segtool.undo()
            self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)

    def dilate_mask(self):
        try:
            self.iface.mapCanvas().layersChanged.disconnect(self.canvasLayersChanged)
        except Exception as e:
            print_log("Exception occured in monitask.seg_finished:",e)
        finally:
            if self.seg_status:
                self.segtool.adjust_mask(1)
            self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)


    def erode_mask(self):
        try:
            self.iface.mapCanvas().layersChanged.disconnect(self.canvasLayersChanged)
        except Exception as e:
            print_log("Exception occured in monitask.seg_finished:",e)
        finally:
            if self.seg_status:
                self.segtool.adjust_mask(2)
            self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)


    def getLoadedMapLayerBySourceShortName(self,sourceShortName):
        targetlayer=None
        layers= QgsProject.instance().mapLayers()
        for layer in layers.values():
            if layer.source().find(sourceShortName)>0:
                targetlayer=layer
                break
        return targetlayer

    def showPreimgInOtherView(self):
        root = QgsProject.instance().layerTreeRoot()
        mapThemesCollection = QgsProject.instance().mapThemeCollection()
        mapThemes = mapThemesCollection.mapThemes()

        for child in root.children():
            if isinstance(child, QgsLayerTreeGroup):
                # print_log("- group: " + child.name())
                if child.name()=='后时相影像':
                    child.setItemVisibilityChecked(False)
                    break
        mapThemeRecord = QgsMapThemeCollection.createThemeFromCurrentState(QgsProject.instance().layerTreeRoot(),
                                                                            self.iface.layerTreeView().layerTreeModel())
        mapThemesCollection.insert('preimg', mapThemeRecord)

        preimg_mapview = None
        for canvas in self.iface.mapCanvases():
            if canvas.objectName()=='Map 1': preimg_mapview = canvas

        if preimg_mapview == None:
            self.iface.mainWindow().findChild(QObject, 'mActionNewMapCanvas').trigger()
            preimg_mapview = self.iface.mainWindow().findChild(QWidget, 'Map 1')
            preimg_mapview.parent().parent().parent().setWindowTitle('前时相影像')

        preimg_mapview.setTheme('preimg')
        preimg_mapview.setCenter(self.iface.mapCanvas().center())
        preimg_mapview.zoomScale(self.iface.mapCanvas().scale())
        self.iface.mapCanvas().extentsChanged.connect(self.syncPreImgViewCenterWithMainView)
        self.iface.mapCanvas().scaleChanged.connect(self.syncPreImgViewScaleWithMainView)
        preimg_mapview.parent().parent().parent().show()

    def syncPreImgViewCenterWithMainView(self):
        preimg_mapview=self.iface.mainWindow().findChild(QWidget, 'Map 1')
        if preimg_mapview:
            preimg_mapview.setCenter(self.iface.mapCanvas().center())
            preimg_mapview.refresh()

    def syncPreImgViewScaleWithMainView(self):
        preimg_mapview=self.iface.mainWindow().findChild(QWidget, 'Map 1')
        if preimg_mapview:
            preimg_mapview.zoomScale(self.iface.mapCanvas().scale())
            preimg_mapview.refresh()

    def showCanvasContextMenu(self, menu, event):
        menu.clear()
        menu.addAction(self.gridstatus_action2)
        menu.addAction(self.gridstatus_action1)
        menu.addAction(self.gridstatus_action0)
#        self.iface.statusBarIface().showMessage(str(res))
        task_grid_layer=self.getLoadedMapLayerBySourceShortName('task_grid')
        if task_grid_layer:
            taskgrids=task_grid_layer.getFeatures()
            for grid in taskgrids:
                if grid.geometry().contains(QgsGeometry.fromPointXY(event.mapPoint())):
                    task_grid_layer.removeSelection()
                    task_grid_layer.select(grid.id())
                    self.task_grid_layer=task_grid_layer
                    self.selected_grid_id=grid.id()
                    break

    def setSelectedGridStatus(self,status):
        self.task_grid_layer.startEditing()
        dt_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.task_grid_layer.changeAttributeValue(self.selected_grid_id,2,status)
        self.task_grid_layer.changeAttributeValue(self.selected_grid_id,4,dt_str)
        # self.task_grid_layer.select(self.selected_grid_id)
        # features=self.task_grid_layer.selectedFeatures()
        # for feature in features:
        #     feature["status"]=status
        #     QMessageBox.about(None, 'about', str(feature["status"]))
        ret=self.task_grid_layer.commitChanges(True)
        if not ret:
            self.task_grid_layer.endEditCommand()
            QMessageBox.about(None, 'about', str(self.task_grid_layer.commitErrors()))
        self.task_grid_layer.removeSelection()

    def setgridstatus_finished(self):
        self.setSelectedGridStatus(2)
    def setgridstatus_tobecontinue(self):
        self.setSelectedGridStatus(1)
    def setgridstatus_waittostart(self):
        self.setSelectedGridStatus(0)

    def showLabelWidget(self):
        icon_path = ':/plugins/monitask/icon.png'
        icon = QIcon(icon_path)
        self.labelWidget.setWindowIcon(icon)

        #load labels
        self.labelWidget.labelBaseFile=self.settingsObj.General_labelDBFile
        print(self.settingsObj.General_labelDBFile)

        self.labelWidget.canvasLayersChanged()
        if type(self.settingsObj.Advanced_oneshot_threshold)==int:
            self.labelWidget.pass_thresh_spinBox.setValue(self.settingsObj.Advanced_oneshot_threshold)
        else:
            self.labelWidget.pass_thresh_spinBox.setValue(90)
        if type(self.settingsObj.Advanced_candidate_threshold)==int:
            self.labelWidget.candidate_thresh_spinBox.setValue(self.settingsObj.Advanced_candidate_threshold)
        else:
            self.labelWidget.candidate_thresh_spinBox.setValue(66)

        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.labelWidget)
        self.iface.mapCanvas().layersChanged.connect(self.canvasLayersChanged)

        if self.labelWidget.labelBaseFile.strip()=="":
            self.settingsDlg.tabWidget.setCurrentIndex(1)
            self.settingsDlg.focusOnLabelbase()
            self.showSettingsDlg()


    def isOKForOutputLayer(self,qgslayer):
        '''
        TODO: to be finished
        检查layer中的各个字段是否符合设置中对输出图层的字段要求
        '''
        isOk=0
        #如果未设置字段要求，提示设置，并显示设置窗口，将焦点切换到设置部分
        field_settings=self.settingsObj.General_outLayerFields
        if field_settings.strip():
            field_settings=eval(field_settings)
            for field in qgslayer.fields():
                for required_filed in field_settings:
                    if required_filed[5]=="Labeling" and field.name()==required_filed[0] and field.typeName()==required_filed[1]:
                        isOk += 1
        else:
            self.showSettingsDlg()
            self.settingsDlg.fieldNameEdit.setFocus()
        return isOk

    def showTaskDialog(self):
        self.task_widget = TaskDialog()
#        self.task_widget.setWindowModality(Qt.NonModal)
#        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.task_widget)
        icon_path = ':/plugins/monitask/icon.png'
        icon = QIcon(icon_path)
        self.task_widget.setWindowIcon(icon)
        self.task_widget.setContext(self.iface)
        self.task_widget.accepted.connect(self.configChangeLayerSlot)
        self.task_widget.show()

    def configChangeLayerSlot(self):
        changelayer=self.getLoadedMapLayerBySourceShortName('change_parcels')
        if changelayer:
            changelayer.featureAdded.connect(self.changeLayerFeatureAdded)
            changelayer.dataChanged.connect(self.changeLayerAttributeChanged)
            changelayer.editingStopped.connect(self.changeLayerEditingStopped)
            changelayer.layerModified.connect(self.changeLayerModified)
            self.iface.layerTreeView().collapseAllNodes()
            self.setDefaultSnappingConfig()
            self.iface.setActiveLayer(changelayer)
            changelayer.startEditing()

    def setDefaultSnappingConfig(self):
        is_default=True
        current_snapConfig=QgsProject.instance().snappingConfig()
        if current_snapConfig:
            current_snapConfig.setTolerance(5)
            current_snapConfig.setUnits(QgsTolerance.Pixels)
            if not current_snapConfig.enabled():
                current_snapConfig.setEnabled(True)
                is_default=False
            if current_snapConfig.mode()!=QgsSnappingConfig.ActiveLayer:
                #current_snapConfig.setMode(QgsSnappingConfig.ActiveLayer)
                current_snapConfig.setMode(Qgis.SnappingMode(Qgis.SnappingMode.ActiveLayer))  # ActiveLayer
                is_default = False
            if current_snapConfig.typeFlag()!=Qgis.SnappingType.SegmentFlag:
                current_snapConfig.setTypeFlag(Qgis.SnappingType(Qgis.SnappingType.SegmentFlag))  #
                is_default = False
            if not current_snapConfig.intersectionSnapping():
                current_snapConfig.setIntersectionSnapping(True)
                is_default = False
            if not is_default:
                QgsProject.instance().setSnappingConfig(current_snapConfig)
        else:
            snapConfig = QgsSnappingConfig()
            snapConfig.setEnabled(True)
            snapConfig.setMode(Qgis.SnappingMode(Qgis.SnappingMode.ActiveLayer))  # ActiveLayer
            snapConfig.setTypeFlag(Qgis.SnappingType(Qgis.SnappingType.SegmentFlag))  #
            snapConfig.setIntersectionSnapping(True)
            snapConfig.setTolerance(5)
            snapConfig.setUnits(QgsTolerance.Pixels)
            QgsProject.instance().setSnappingConfig(snapConfig)

        if QgsProject.instance().avoidIntersectionsMode()!=QgsProject.AvoidIntersectionsMode.AvoidIntersectionsCurrentLayer:
            QgsProject.instance().setAvoidIntersectionsMode(QgsProject.AvoidIntersectionsMode.AvoidIntersectionsCurrentLayer)
        if not QgsProject.instance().topologicalEditing():
            QgsProject.instance().setTopologicalEditing(True)

    def changeLayerFeatureAdded(self,fid):
        if fid>0: return
        changelayer=self.getLoadedMapLayerBySourceShortName('change_parcels')
        geometry=changelayer.getGeometry(fid)
        if not geometry.isGeosValid():
            QMessageBox.about(None, '信息-几何无效','(Todo) 几何要素无效，将取消。')
            changelayer.deleteFeature(fid)
            return

        centid=geometry.centroid()
        bgImages=[]
#        QMessageBox.about(None, '信息-几何中心', str(centid))

        idweget = QgsMapToolIdentify(self.iface.mapCanvas())
        idresults = idweget.identify(centid, QgsMapToolIdentify.TopDownAll,
                                     QgsMapToolIdentify.RasterLayer, QgsIdentifyContext())
        for rslt in idresults:
            bgImages.append(os.path.basename(rslt.mLayer.source()))
        if len(bgImages)>=2:
#            QMessageBox.about(None, '信息-影像', str(bgImages))
            preimg =bgImages[1]
            nextimg=bgImages[0]
        else:
            preimg =''
            nextimg=''

        capture_person=self.settingsObj.User_username
        capture_org = self.settingsObj.User_orgname

        task_no= QgsProject.instance().baseName()
        used_scale=self.iface.mapCanvas().mapSettings().scale()
        used_res=self.iface.mapCanvas().mapSettings().mapUnitsPerPixel()
        changelayer.changeAttributeValue(fid,5,  used_res)
        changelayer.changeAttributeValue(fid,6,  used_scale)
        changelayer.changeAttributeValue(fid,7,  task_no)
        changelayer.changeAttributeValue(fid,8,  preimg)
        changelayer.changeAttributeValue(fid,9,  nextimg)
        # changelayer.changeAttributeValue(fid,10,  pre_url)
        # changelayer.changeAttributeValue(fid,11,  next_url)
        changelayer.changeAttributeValue(fid,12,  capture_person)
        changelayer.changeAttributeValue(fid,13,  capture_org)
        # changelayer.changeAttributeValue(fid,15,  check_person)

        #changelayer.commitChanges(True) or changelayer.endEditCommand()

    def changeLayerModified(self):
#        QMessageBox.about(None, '信息', 'Layer data has been changed')
        pass


    def changeLayerEditingStopped(self):
#        QMessageBox.about(None, '信息', 'Editting stopped')
        pass

    def changeLayerAttributeChanged(self):
#        QMessageBox.about(None, '信息', 'Attribute value changed')
        pass

    def showSettingsDlg(self):
        if self.settingsDlg is None:
            self.settingsDlg = SettingsDialog()
        else:
            self.settingsDlg.loadSettings()
#        self.settingsDlg.setWindowModality(Qt.NonModal)
        icon_path = ':/plugins/monitask/icon.png'
        icon = QIcon(icon_path)
        self.settingsDlg.setWindowIcon(icon)
        if self.lb:
            lb_meta= self.lb.getMetaInfo()
            if lb_meta:
                self.settingsDlg.ls_descEdit.setPlainText(lb_meta[3])

        #由于目前暂时不使用，先关闭network和preference两个Tab
        self.settingsDlg.tabWidget.setTabVisible(3,False)
        self.settingsDlg.tabWidget.setTabVisible(4,False)

        ret=self.settingsDlg.exec_()
        self.reload_settings()
        self.reload_labelbase()
        self.lb.logMetaInfo(self.settingsObj.User_username, self.settingsObj.User_orgname)
        if self.labelWidget.isVisible():
            self.labelWidget.reloadLabelBase()


    def reload_settings(self):
        self.settingsObj=None
        self.settingsObj=SettingsClass(os.path.dirname(__file__) + "\\monitask_config.ini", SettingsClass.IniFormat)

    def reload_labelbase(self):
        self.lb=None
        self.lb=LabelBase(self.settingsObj.General_labelDBFile)


    def submit(self):
        pass


    def writeCustomExpressionFunctions(self):
        userProfileRoot=QgsApplication.qgisSettingsDirPath()
        #将plugins/monitask下的monitask_ExpFunc.py拷贝到expressions目录下

    def getRecentUsedLabel(self,minutes_passed=30):
        import time
        now=time.time()
        recent=float(self.settingsObj.User_RecentUsedLabelTime) if self.settingsObj.User_RecentUsedLabelTime else now
        labelTitle = self.settingsObj.User_RecentUsedLabel if self.settingsObj.User_RecentUsedLabel else None
        labelId = int(self.settingsObj.User_RecentUsedLabelID) if self.settingsObj.User_RecentUsedLabelID else 0
        if now-recent<=minutes_passed*60:
            return LabelItem(labelTitle,labelId,-1,'','',[])
        else:
            return None

    def setRecentUsedLabel(self,labelTitle,labelId):
        import time
        self.settingsObj.User_RecentUsedLabel=labelTitle
        self.settingsObj.User_RecentUsedLabelID=str(labelId)
        self.settingsObj.User_RecentUsedLabelTime=str(time.time())
        self.labelWidget.focuslabel(labelId)

    def getMostUsedLabels(self,min_used=1):
        return self.lb.getMostUsedLabelItems(min_used)


    def incedentLabelUsedTimes(self,labelid,used_times=1):
        self.lb.incedentLabelUsedTimes(labelid,used_times)

    def test_change_detect(self):
        if not self.changedetect_action.isChecked():
            #self.wl.setPrevImageLayer(None)
            #self.segtool.CD_InProcessing=True
            self.iface.mapCanvas().extentsChanged.disconnect(self.segtool.detect_changes)
            self.labelWidget.enablePrevImgInputs(False)
            #self.iface.mapCanvas().scaleChanged.disconnect(self.segtool.canvasMovedAgain_ByScale)
            #self.iface.mapCanvas().panDistanceBearingChanged.disconnect(self.segtool.canvasMovedAgain_ByPan)
            return
        # check if exist more than 1 rasterlayer
        self.labelWidget.enablePrevImgInputs(True)
        if not hasattr(self.wl, "previmg_layer") or self.wl.previmg_layer is  None:
            layers = QgsProject.instance().mapLayers().values()
            for layer in layers:
                layerType = layer.type()
                if layerType == QgsMapLayer.RasterLayer and layer.flags() != QgsMapLayer.Private:
                    try:
                        if layer.name() != self.wl.baseimg_layer.name():
                            self.wl.setPrevImageLayer(layer)
                        else:
                            try_name = self.wl.previmg_layer.name()
                    except:
                        # print_log("----monitask.wl.baseimg_layer not exist")
                        self.wl.setPrevImageLayer(layer)
        try: #通过异常判断changedetected_layer是否存在，如果被手动删除，self.wl.changedetected_layer is None无法识别
            cd_layer_deleted = False
            try_name=self.wl.changedetected_layer.name()
        except:
            cd_layer_deleted=True
        if not hasattr(self.wl, "changedetected_layer") or self.wl.changedetected_layer is None or cd_layer_deleted:
            cd_layer = newDetectedChangesLayer(self.settingsObj,None, self.wl.crs)
            if cd_layer:
                self.wl.setCDLayer(cd_layer)
                self.setCDLayerDefaultSymbol(cd_layer,opacityField="csim",labelField="csim")
                QgsProject.instance().addMapLayer(cd_layer)

        if self.wl.previmg_layer is not None:
            self.iface.mapCanvas().extentsChanged.connect(self.segtool.detect_changes)
            #self.iface.mapCanvas().scaleChanged.connect(self.segtool.canvasMovedAgain_ByScale)
            #self.iface.mapCanvas().panDistanceBearingChanged.connect(self.segtool.canvasMovedAgain_ByPan)


    def setCDLayerDefaultSymbol(self,targetLayer,opacityField="csim",labelField="csim"):
        # create from a defaultsymbol:
        symbol = QgsSymbol.defaultSymbol(targetLayer.geometryType())
        # Create all style layers
        symL1 = QgsSimpleFillSymbolLayer.create({
            'type':"fill",
            'color': "14,106,49,255",
            "outline_color": "170,0,0,255",
            "outline_width": "0.4",
            "style": "solid"
        })
        symbol.setDataDefinedProperty(QgsSymbol.PropertyOpacity, QgsProperty.fromExpression('("'+opacityField+'"-60)/30*100'))
        symbol.changeSymbolLayer(0, symL1)
        # Create a renderer with the symbol as first parameter
        renderer = QgsSingleSymbolRenderer(symbol)
        # Define the renderer
        targetLayer.setRenderer(renderer)
        #setting label
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", 11))
        text_format.setSize(11)
        text_format.setColor(QColor(249,234,17,255))
        layer_settings = QgsPalLayerSettings()
        layer_settings.setFormat(text_format)
        layer_settings.fieldName = labelField
        layer_settings.enabled = True
        layer_settings = QgsVectorLayerSimpleLabeling(layer_settings)
        targetLayer.setLabelsEnabled(True)
        targetLayer.setLabeling(layer_settings)

