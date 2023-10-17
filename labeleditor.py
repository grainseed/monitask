# -*- coding: utf-8 -*-
from qgis.PyQt import QtGui, QtWidgets, uic,QtNetwork
from qgis.core import Qgis,QgsProject,QgsMapLayerType,QgsMapLayer,QgsWkbTypes
from qgis.PyQt.QtCore import Qt,QSettings
from qgis.PyQt.QtWidgets import QMessageBox, QTreeWidgetItem,QApplication,QTreeWidgetItemIterator
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.gui  import QgsDataSourceSelectDialog,QgsDockWidget

import os
import sqlite3
from .settings import SettingsClass
from .utils import newOutLayer,isOutputLayerValid,getLayerByTile,setParcelDefaultSymbol,print_log
from .labelbase import LabelItem
import time

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'labeleditor.ui'))


class LabelEditor(QgsDockWidget, FORM_CLASS):
    def __init__(self, monitask,parent=None):
        """Constructor."""
        super(LabelEditor, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.monitask=monitask
        self.iface=monitask.iface
        self.baseImgLayer=None
        self.outputLayer=None
        self.labelBaseFile=None
        self.candidate_choosed=-1

        self.baseImg_comboBox.currentTextChanged.connect(self.baseMapComboTextChanged)
        self.prevImg_comboBox.currentTextChanged.connect(self.prevImgComboTextChanged)
        self.outlayer_comboBox.currentTextChanged.connect(self.outLayerComboxTextChanged)
        self.label_list.itemClicked.connect(self.labelListItemClicked)
        self.label_list.itemDoubleClicked.connect(self.label_listDoubleClicked)
        self.newLabelButton.clicked.connect(self.newLabelItem)

        self.addToRuleList.clicked.connect(self.addSelectedRule)
        self.delFromRuleList.clicked.connect(self.delSelectedRule)
        self.clearRuleList.clicked.connect(self.clearRules)

        self.visibilityChanged.connect(self.fillLabelList)

        self.loadBaseImgButton.clicked.connect(self.loadBaseImage)
        self.loadPrevImgButton.clicked.connect(self.loadPrevImage)

        self.loadOutputLayerButton.clicked.connect(self.loadOutputLayer)
        self.newOutputLayerButton.clicked.connect(self.newOutputLayer)
        self.candidate_treeWidget.itemDoubleClicked.connect(self.candidateDoubleClicked)

        self.chooseButton.clicked.connect(self.candidateChosen)
        self.noProper_Button.clicked.connect(self.candidateAbandoned)
        self.applyChangeButton.clicked.connect(self.saveLabelProperties)
        self.reloadLBButton.clicked.connect(self.reloadLabelBase)
        self.delLabelButton.clicked.connect(self.delSelectedLabel)

        self.lblFilter_lineEdit.textChanged.connect(self.lblFilterChanged)

        self.pass_thresh_spinBox.valueChanged.connect(self.pass_thresh_changed)
        self.candidate_thresh_spinBox.valueChanged.connect(self.candidate_thresh_changed)

    def pass_thresh_changed(self,value):
        self.monitask.settingsObj.Advanced_oneshot_threshold=value

    def candidate_thresh_changed(self, value):
        self.monitask.settingsObj.Advanced_candidate_threshold=value

    def lblFilterChanged(self,qsFilter):
       # qsFilter需要搜索的文字
        cursor = QTreeWidgetItemIterator(self.label_list)
        while cursor.value():
            item=cursor.value()
            if qsFilter.strip() in item.text(0):
                item.setHidden(False)
                # 需要让父节点也显示,不然子节点显示不出来
                try:
                    p=item
                    while p.parent():
                        p.parent().setHidden(False)
                        p=p.parent()
                except Exception as e:
                    print_log("Exception occured in labeleditor.lblFilterChanged:",e)
            else:
                item.setHidden(True)
            cursor+=1

    def loadBaseImage(self):
        loaddialog = QgsDataSourceSelectDialog(None,True,QgsMapLayerType.RasterLayer,self)
        loaddialog.exec_()
        uri=loaddialog.uri()
        layer=uri.rasterLayer("not available")[0]
        self.monitask.workingLayersChanged(baseimg_layer=layer)
        QgsProject.instance().addMapLayer(layer)

    def loadPrevImage(self):
        loaddialog = QgsDataSourceSelectDialog(None,True,QgsMapLayerType.RasterLayer,self)
        loaddialog.exec_()
        uri=loaddialog.uri()
        layer=uri.rasterLayer("not available")[0]
        self.monitask.workingLayersChanged(previmg_layer=layer)
        QgsProject.instance().addMapLayer(layer)

    def loadOutputLayer(self):
        loaddialog = QgsDataSourceSelectDialog(None,True,QgsMapLayerType.VectorLayer,self)
        loaddialog.exec_()
        uri=loaddialog.uri()
        layer=uri.vectorLayer("not available")[0]
        if layer and isOutputLayerValid(layer,self.monitask.settingsObj):
            self.monitask.workingLayersChanged(output_layer=layer)
            QgsProject.instance().addMapLayer(layer)

    def newOutputLayer(self):
        if self.outlayer_comboBox.findText(self.outlayer_comboBox.currentText()) == -1:
            layer=newOutLayer(self.monitask.settingsObj,self.outlayer_comboBox.currentText(),self.monitask.wl.crs)
            if layer:
                self.monitask.workingLayersChanged(output_layer=layer)
                setParcelDefaultSymbol(layer)
                QgsProject.instance().addMapLayer(layer)

    def addSelectedRule(self):
        if self.listWidget.currentRow()>-1:
            existing=self.ruleList.findItems(self.listWidget.currentItem().text(),Qt.MatchExactly)
            if len(existing)<1:
                self.ruleList.addItem(self.listWidget.currentItem().text())

    def delSelectedRule(self):
        if self.ruleList.currentRow()>-1:
            self.ruleList.takeItem(self.ruleList.currentRow())

    def clearRules(self):
        self.ruleList.clear()

    def saveLabelProperties(self):
        cur_item=self.label_list.currentItem()
        if int(cur_item.text(1))>=0:
            title = self.newLabelText_lineEdit.text()
            id=int(self.labelId.text())
            parentid=self.superLabelId.text()
            cc=self.labelCode.text()
            description=self.labelDesc.toPlainText()
            reshape_rule=[]
            item_count = self.ruleList.count()
            for i in range(item_count):
                reshape_rule.append(self.ruleList.item(i).text())
            self.monitask.lb.updateLabelItem(LabelItem(title,id,parentid,cc,description,reshape_rule))
        self.fillLabelList(True)
        self.label_list.setCurrentItem(self.label_list.findItems("{:0>3d}".format(id),Qt.MatchExactly|Qt.MatchRecursive,column=1)[0])
        self.fillLabelForms(self.monitask.lb.getLabelItemById(int(id)))
        self.label_list.resizeColumnToContents(0)

    def reloadLabelBase(self):
        self.monitask.reload_settings()
        self.monitask.reload_labelbase()
        self.labelBaseFile=self.monitask.settingsObj.General_labelDBFile
        self.fillLabelList(True)

    def delSelectedLabel(self):
        cur_item=self.label_list.currentItem()
        if int(cur_item.text(1))>=0:
            msg = QMessageBox()
            msg.setWindowTitle("Message Box")
            msg.setText("If you delete this label, records using this label will not be removed, you'd better change it as expect.")
            msg.setInformativeText("Delete it anyway?")
            msg.setIcon(QMessageBox.Question)
            msg.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
            msg.setDefaultButton(QMessageBox.No)
            x = msg.exec_()
            if x==QMessageBox.Yes:
                self.monitask.lb.delteLabelItem(int(cur_item.text(1)))

                self.fillLabelList(True)
                if len(self.monitask.lb.labelItems) > 0:
                    self.label_list.setCurrentItem(self.label_list.topLevelItem(0))
                    self.fillLabelForms(self.monitask.lb.labelItems[0])
                    self.label_list.resizeColumnToContents(0)

    def focusOutEvent(self,e):
        pass

    def checkWorkEnv(self):
        '''
        检查以来的相关信息的正确性：包括输出图层结构是否符合设置中的要求；label库是否已设置。如果未设置，自动计入设置界面，并蒋焦点舍之道相应位置。
        '''
        pass

    def fillLabelList(self,visible=True):
        if self.labelBaseFile is None or self.labelBaseFile.strip()=="":
            self.showKeyStatus("No label system available,please specify it in Settings")

        elif visible:
            self.showKeyStatus("Notice")
            self.label_list.clear()
            self.label_list.setColumnCount(2)
            # 设置头的标题
            self.label_list.setHeaderLabels(['Title', 'ID'])
            childs=[]
            for label in self.monitask.lb.labelItems:
                if label.superid<0:
                    node = QTreeWidgetItem(self.label_list)
                    node.setText(0, label.title)
                    node.setText(1, "{:0>3d}".format(label.id))
                else:
                    childs.append(label)
            while len(childs)>0:
                for i in range(len(childs)-1,-1,-1):
                    if childs[i].superid>=0:
                        superitem=self.label_list.findItems("{:0>3d}".format(childs[i].superid),Qt.MatchExactly|Qt.MatchRecursive,column=1)
                        if len(superitem)>0:
                            node = QTreeWidgetItem()
                            node.setText(0, childs[i].title)
                            node.setText(1, "{:0>3d}".format(childs[i].id))
                            superitem[0].addChild(node)
                            childs.pop(i)

            self.label_list.sortItems(1, Qt.AscendingOrder)
            self.label_list.resizeColumnToContents(0)
            if len(self.monitask.lb.labelItems)>0:
                self.label_list.setCurrentItem(self.label_list.topLevelItem(0))
                self.fillLabelForms(self.monitask.lb.labelItems[0])
                self.label_list.resizeColumnToContents(0)

    def focuslabel(self,labelId):
        item=self.label_list.findItems("{:0>3d}".format(labelId), Qt.MatchExactly|Qt.MatchRecursive,column=1)
        if len(item)>0:
            self.label_list.setCurrentItem(item[0])
            self.label_list.resizeColumnToContents(0)
        for item in self.monitask.lb.labelItems:
            if item.id == labelId:
                self.fillLabelForms(item)

    def fillLabelForms(self,labelItem):
        self.newLabelText_lineEdit.setText(labelItem.title)
        self.labelId.setText(str(labelItem.id))
        self.superLabelId.setText(str(labelItem.superid))
        self.labelCode.setText(labelItem.cc)
        self.labelDesc.setPlainText(labelItem.desc)
        self.ruleList.clear()
        if labelItem.reshape_rule is not None:
            self.ruleList.addItems(labelItem.reshape_rule)

    def newLabelItem(self):
        labelTxt=self.newLabelText_lineEdit.text().strip()
        if labelTxt=="" or len(self.label_list.findItems(labelTxt,Qt.MatchExactly|Qt.MatchRecursive))>0:
            labelTxt="临时标签(需立即修改)"

        labelItem=LabelItem(labelTxt,None,-1,"","",["SimplifyPreserveTopology"])
        lastid=self.monitask.lb.insertLabelItem(labelItem)

        node = QTreeWidgetItem(self.label_list)
        node.setText(0, labelTxt)
        node.setText(1, str(lastid))
        self.label_list.setCurrentItem(node)
        self.label_list.resizeColumnToContents(0)

        if lastid>-1:
            labelItem=self.monitask.lb.getLabelItemById(lastid)
            self.fillLabelForms(labelItem)
            return labelItem
        else:
            return None


    def showKeyStatus(self,message):
        self.tip.setStyleSheet("color:#ff0000;background-color:#eeee00")
        self.tip.setText(message)


    def baseMapComboTextChanged(self,text):
        if text.strip():
            if getLayerByTile(text.strip()):
                self.monitask.workingLayersChanged(baseimg_layer=text.strip())
                #print_log("set base image to {}".format(text))

    def prevImgComboTextChanged(self,text):
        if text.strip():
            if getLayerByTile(text.strip()):
                self.monitask.workingLayersChanged(previmg_layer=text.strip())
                #print_log("set base image to {}".format(text))

    def enablePrevImgInputs(self,enabled=True):
        self.prevImg_comboBox.setEnabled(enabled)
        self.loadPrevImgButton.setEnabled(enabled)
        if enabled:
            self.canvasLayersChanged()

    def outLayerComboxTextChanged(self,text):
        #print_log("LE: outLayer ComboTextChanged")
        if text.strip():
            l=getLayerByTile(text.strip())
            if l and isOutputLayerValid(l,self.monitask.settingsObj):
                #print_log("LE_outLayerComboxTextChanged:setting outlayer to {}".format(text.strip()))
                self.monitask.workingLayersChanged(output_layer=l)

    def canvasLayersChanged(self):
        '''主窗口图层列表发生变化，通过monitask调用本函数，以便同步更新label窗口的相关控件'''
        #print_log("LE: canvasLayers Changed")
        self.baseImg_comboBox.currentTextChanged.disconnect()
        self.prevImg_comboBox.currentTextChanged.disconnect()
        #print_log("LE: baseImg combobox disconnect")
        self.outlayer_comboBox.currentTextChanged.disconnect()
        #print_log("LE: outlayer combobox disconnect")
        self.baseImg_comboBox.clear()
        self.prevImg_comboBox.clear()
        self.outlayer_comboBox.clear()
        #print_log("LE: combobox cleared")

        layers=QgsProject.instance().mapLayers().values()
        for layer in layers:
            layerType = layer.type()
            if layerType == QgsMapLayer.RasterLayer and layer.flags()!=QgsMapLayer.Private:
                if self.baseImg_comboBox.findText(layer.name())==-1:
                    self.baseImg_comboBox.addItem(layer.name())
                    try:
                        if self.monitask.wl.baseimg_layer is None:
                            #print_log("baseimg_layer is None")
                            self.monitask.wl.setBaseImageLayer(layer)
                        else:
                            try_name=self.monitask.wl.baseimg_layer.name()
                    except:
                        #print_log("----monitask.wl.baseimg_layer not exist")
                        self.monitask.wl.setBaseImageLayer(layer)
                if self.prevImg_comboBox.findText(layer.name())==-1 and layer.name()!=self.monitask.wl.baseimg_layer.name():
                    self.prevImg_comboBox.addItem(layer.name())
                    try:
                        if self.monitask.wl.previmg_layer is None:
                            self.monitask.wl.setPrevImageLayer(layer)
                        else:
                            try_name=self.monitask.wl.previmg_layer.name()
                    except:
                        #print_log("----monitask.wl.baseimg_layer not exist")
                        self.monitask.wl.setPrevImageLayer(layer)

            elif layerType == QgsMapLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry and layer.flags()!=QgsMapLayer.Private:
                if isOutputLayerValid(layer,self.monitask.settingsObj):
                    if self.outlayer_comboBox.findText(layer.name()) == -1:
                        self.outlayer_comboBox.addItem(layer.name())
                        try:
                            if self.monitask.wl.output_layer is None:
                                #print_log("output_layer is None")
                                self.monitask.wl.setOutputLayer(layer)
                            else:
                                try_name=self.monitask.wl.output_layer.name()
                        except:
                            #print_log("----monitask.wl.output_layer not exist")
                            self.monitask.wl.setOutputLayer(layer)

            elif layer.flags()==QgsMapLayer.Private:
                pass
                #print_log("-----private layer: "+layer.name())

        if self.baseImg_comboBox.count()==1:
            self.baseImg_comboBox.setCurrentIndex(0)
            self.prevImg_comboBox.setEnabled(False)
            self.monitask.changedetect_action.setDisabled(True)
        elif self.baseImg_comboBox.count()>1:
            index=self.baseImg_comboBox.findText(self.monitask.wl.baseimg_layer.name())
            #print_log("index:"+str(index))
            self.baseImg_comboBox.setCurrentIndex(index)
            #print_log("the current baseimg is {}, index is {}".format(self.monitask.wl.baseimg_layer.name(),index))
            self.prevImg_comboBox.setEnabled(True)
            self.monitask.changedetect_action.setDisabled(False)
        else:
            self.loadBaseImgButton.setFocus()

        # if self.prevImg_comboBox.count()==1:
        #     self.prevImg_comboBox.setCurrentIndex(0)
        #     self.prevImg_comboBox.setEnabled(True)
        #     self.monitask.changedetect_action.setDisabled(False)
        # el
        if self.prevImg_comboBox.count()>=1:
            index=self.prevImg_comboBox.findText(self.monitask.wl.previmg_layer.name())
            #print_log("index:"+str(index))
            self.prevImg_comboBox.setCurrentIndex(index)
            #print_log("the current baseimg is {}, index is {}".format(self.monitask.wl.baseimg_layer.name(),index))
            self.prevImg_comboBox.setEnabled(True)
            self.monitask.changedetect_action.setDisabled(False)
        else:
            self.loadPrevImgButton.setFocus()
            self.prevImg_comboBox.setCurrentIndex(-1)

        #print_log("count of outlayer:"+str(self.outlayer_comboBox.count()))
        if self.outlayer_comboBox.count()==1:
            self.outlayer_comboBox.setCurrentIndex(0)
        elif self.outlayer_comboBox.count()>1:
            index=self.outlayer_comboBox.findText(self.monitask.wl.output_layer.name())
            self.outlayer_comboBox.setCurrentIndex(index)
            #print_log("the current output_layer is {}, index is {}".format(self.monitask.wl.output_layer.name(),index))
        else:
            if str(self.monitask.settingsObj.General_autoNewOutLayer).upper()=="TRUE":
                outlayer=newOutLayer(self.monitask.settingsObj)
                if outlayer:
                    self.monitask.wl.setOutputLayer(outlayer)
                    setParcelDefaultSymbol(outlayer)
                    QgsProject.instance().addMapLayer(outlayer)
                    self.outlayer_comboBox.addItem(outlayer.name())
                    self.outlayer_comboBox.setCurrentIndex(0)
                else:
                    self.newOutputLayerButton.setFocus()
                    #print_log("new layer failed")
            else:
                self.loadOutputLayerButton.setFocus()
        self.baseImg_comboBox.currentTextChanged.connect(self.baseMapComboTextChanged)
        self.prevImg_comboBox.currentTextChanged.connect(self.prevImgComboTextChanged)
        self.outlayer_comboBox.currentTextChanged.connect(self.outLayerComboxTextChanged)


    def labelListItemClicked(self,item,column):
        self.label_list.resizeColumnToContents(0)
        self.showKeyStatus(item.text(0))
        labelItem=self.monitask.lb.getLabelItemById(int(item.text(1)))
        self.fillLabelForms(labelItem)

    def fillCadidateLabels(self,candidates):
        self.candidate_treeWidget.clear()
        self.chooseButton.setEnabled(False)
        self.noProper_Button.setEnabled(False)
        self.candidate_treeWidget.setColumnCount(3)
        self.candidate_treeWidget.setHeaderLabels(["ID", "Title", "Similarity",])
        # 添加数据到模型
        for row in candidates:
            node = QTreeWidgetItem(self.candidate_treeWidget)
            node.setText(0, str(row[0]))
            node.setText(1, row[1])
            node.setText(2, "{:.2f}".format(row[2]))
        if len(candidates):
            self.chooseButton.setEnabled(True)
            self.noProper_Button.setEnabled(True)
        self.candidate_treeWidget.resizeColumnToContents(1)

    def candidateDoubleClicked(self,item,column):
        self.showKeyStatus("选择了{}。".format(item.text(1)))
        self.candidate_choosed=1  #做出了选择

    def label_listDoubleClicked(self,item,column):
        self.candidate_choosed=2  #做出了选择
        feats=self.monitask.wl.output_layer.selectedFeatures()
        #print_log(len(feats))
        lblFld=self.monitask.segtool.getLabelingFieldName()
        if len(feats)>0:
            self.monitask.wl.output_layer.startEditing()
            for feat in feats:
                feat[lblFld]=int(item.text(1))
                self.monitask.wl.output_layer.updateFeature(feat)
                self.showKeyStatus("当前选中要素修改为{}。".format(item.text(0)))
                #self.monitask.wl.output_layer.changeAttributeValue(feat["fid"],1, item.text(1))
                self.monitask.lb.updateLabelSampleLabelid(feat["fid"],int(item.text(1)))
            self.monitask.wl.output_layer.commitChanges()

    def candidateChosen(self):
        self.candidate_choosed=1  #做出了选择
        self.showKeyStatus("已选择")

    def candidateAbandoned(self):
        self.candidate_choosed=0  #主动放弃选择
        self.showKeyStatus("放弃")


    def getLabelItemFromCandidates(self,wait_seconds=60):
        self.showKeyStatus("请在{}秒内从候选标签或标签全集中选择，过时将自动选择。".format(wait_seconds))
        self.candidate_choosed = -1
        self.candidate_treeWidget.setFocus()
        self.candidate_treeWidget.sortItems(2,Qt.DescendingOrder)
        time_passed=0
        start=time.time()

        while self.candidate_choosed==-1 and time_passed<wait_seconds:
            QApplication.processEvents()
            time_passed=time.time()-start
            self.showKeyStatus("过去了{:.1f}秒...".format(time_passed))
            time.sleep(0.1)
            if not self.isVisible():
                break

        if self.candidate_choosed==1:
            item =self.candidate_treeWidget.currentItem()
            if item is None:
                item=self.candidate_treeWidget.topLevelItem(0)
            self.showKeyStatus("{}(id={}) is chosen.".format(item.text(1),item.text(0)))
            labelitem= self.monitask.lb.getLabelItemById(int(item.text(0)))
        elif self.candidate_choosed==2: #从完整列表中选择
            item =self.label_list.currentItem()
            if item is None:
                labelitem=None
            else:
                self.showKeyStatus("{}(id={}) is chosen.".format(item.text(0),item.text(1)))
                labelitem= self.monitask.lb.getLabelItemById(int(item.text(1)))
        elif self.candidate_choosed==0:  #放弃选择
            labelitem = None
            self.showKeyStatus("You abandoned choosing.")
        else:#self.candidate_choosed==-1
            self.showKeyStatus("Time out, You missed choosing.")
            labelitem = None

        self.candidate_treeWidget.clear()
        self.candidate_choosed = -1 #重置为未做选择的状态
        self.chooseButton.setEnabled(False)
        self.noProper_Button.setEnabled(False)
        return labelitem









