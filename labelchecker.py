# -*- coding: utf-8 -*-
from qgis.PyQt import QtGui, QtWidgets, uic,QtNetwork
from qgis.core import Qgis,QgsProject,QgsMapLayerType,QgsMapLayer,QgsWkbTypes,QgsPointXY
from qgis.PyQt.QtCore import Qt,QSettings
from qgis.PyQt.QtWidgets import QMessageBox, QTreeWidgetItem,QApplication,QTreeWidgetItemIterator
# from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.gui  import QgsDataSourceSelectDialog,QgsDockWidget

import os
# import sqlite3
# from .settings import SettingsClass
from .utils import FocusCanvasItem
# from .labelbase import LabelItem
# import time

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'labelchecker.ui'))


class LabelChecker(QgsDockWidget, FORM_CLASS):
    def __init__(self, monitask,parent=None):
        """Constructor."""
        super(LabelChecker, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.currentSampId=-1
        self.currentLabelId=-1
        self.currentLayerName=None
        self.filteredSamples=[]
        self.setupUi(self)
        self.monitask=monitask
        self.runButton.clicked.connect(self.runOperation)
        self.thresh_spin.valueChanged.connect(self.runOperation)
        self.samplesTreeWidget.doubleClicked.connect(self.panToSampleCenter)
        self.panbackButton.clicked.connect(self.panBack)
        self.operationTypeCombo.currentIndexChanged.connect(self.onOperationSelected)
        self.methodCombo.currentIndexChanged.connect(self.onMethodSelected)

    def onMethodSelected(self,currentIndex):
        if currentIndex<=0:#OPTICS
            self.label_2.setText("Max Esp:")
            self.label_2.setEnabled(True)
            self.maxesp_spinBox.setEnabled(True)
        elif currentIndex==1:#HDBSCAN
            self.label_2.setEnabled(False)
            self.maxesp_spinBox.setEnabled(False)
        elif currentIndex==2:#DBSCAN
            self.label_2.setText("Esp:")
            self.label_2.setEnabled(True)
            self.maxesp_spinBox.setEnabled(True)

    def onOperationSelected(self,currentIndex):
        if currentIndex<=1:
            self.op_settings_tabWidget.setCurrentIndex(0)
        else:
            self.op_settings_tabWidget.setCurrentIndex(1)

    def runOperation(self):
        if self.operationTypeCombo.currentIndex()==0:
            self.getOddSampleOfCurrentLabel()
        elif self.operationTypeCombo.currentIndex()==1:
            self.getSimSampleOfOtherLabel()
        elif self.operationTypeCombo.currentIndex()==2:
            self.clusteringSamplesOfCurrentLabel()

    def fillSamplesTree(self,samples):
        self.samplesTreeWidget.setColumnCount(3)
        # 设置头的标题
        self.samplesTreeWidget.setToolTip("Similarity: the max similarity between sample and all kinds of label represitative samples")
        self.samplesTreeWidget.setHeaderLabels(['SampleId', 'LabelId', 'Similarity'])
        for sample in samples:
            node = QTreeWidgetItem(self.samplesTreeWidget)
            node.setText(0, str(sample[0]))
            node.setText(1, str(sample[1]))
            node.setText(2, "{:.2f}".format(sample[2]))
        self.samplesTreeWidget.sortItems(2, Qt.DescendingOrder)
        self.samplesTreeWidget.resizeColumnToContents(0)

    def getOddSampleOfCurrentLabel(self):
        # print_log(self.currentSampId,self.currentLabelId,self.currentLayerName)
        if self.currentSampId > -1 and self.currentLabelId > -1:
            self.samplesTreeWidget.clear()
            sim_threshhold=self.thresh_spin.value()
            oddsamples=self.monitask.lb.getOddSamplesOfLabel(self.currentLayerName,self.currentSampId,self.currentLabelId,sim_threshhold)
            if oddsamples:
                self.filteredSamples.clear()
                self.filteredSamples.extend(oddsamples)
                self.fillSamplesTree(oddsamples)

    def getSimSampleOfOtherLabel(self):
        if self.currentSampId > -1 and self.currentLabelId > -1:
            self.samplesTreeWidget.clear()
            sim_threshhold=self.thresh_spin.value()
            # todo
            oddsamples=self.monitask.lb.getSimSamplesOfOtherLabel(self.currentLayerName,self.currentSampId,self.currentLabelId,sim_threshhold)
            if oddsamples:
                self.filteredSamples.clear()
                self.filteredSamples.extend(oddsamples)
                self.fillSamplesTree(oddsamples)

    def clusteringSamplesOfCurrentLabel(self):
        #from sklearn.cluster import DBSCAN,cluster_optics_dbscan
        from sklearn.cluster import OPTICS
        from sklearn.cluster import HDBSCAN
        from sklearn.cluster import DBSCAN

        import numpy as np
        if self.currentSampId > -1 and self.currentLabelId > -1:
            self.samplesTreeWidget.clear()
            labelSamples=self.monitask.lb.getLabelSamplesByLabelId(self.currentLabelId,limit=-1)
            self.filteredSamples.clear()
            if len(labelSamples)>5: #如果样本不多于5个，没必要进行聚类操作
                gebds=[]
                lebds=[]
                sampids=[]
                for samp in labelSamples:
                    gebds.append(samp.gebd)
                    lebds.append(samp.lebd1)
                    sampids.append(samp.id)
                    self.filteredSamples.append((samp.id,self.currentLabelId,0,samp.longitude,samp.latitude))
                if self.srcEbdCombo.currentIndex()==0:
                    X = np.squeeze(np.array(lebds))
                else:
                    X = np.squeeze(np.array(gebds))
                # print_log(X.shape)

                min_samples = self.minsample_spinBox.value()
                if self.methodCombo.currentIndex()==0:# use OPTICS method
                    max_eps = self.maxesp_spinBox.value()
                    OPTICS_clustering = OPTICS(max_eps=max_eps,min_samples=min_samples).fit(X)
                    labels = OPTICS_clustering.labels_[OPTICS_clustering.ordering_]
                    self.fillClusteredSamples(OPTICS_clustering.ordering_,labels,sampids,OPTICS_clustering.reachability_,clustring_method="OPTICS")
                elif self.methodCombo.currentIndex()==1: # use HDBSCAN method
                    hdb = HDBSCAN(min_cluster_size=min_samples,allow_single_cluster=True,store_centers="medoid").fit(X)
                    labels = hdb.labels_
                    #print_log(hdb.labels_,hdb.probabilities_,hdb.medoids_.shape)
                    ordering=np.argsort(labels)
                    self.fillClusteredSamples(ordering,labels[ordering],sampids,hdb.probabilities_[ordering],clustring_method="HDBSCAN")
                else: # use DBSCAN method
                    eps = self.maxesp_spinBox.value()
                    db = DBSCAN(eps=eps,min_samples=min_samples).fit(X)
                    labels = db.labels_
                    ordering=np.argsort(labels)
                    #print_log(db.core_sample_indices_,X[db.core_sample_indices_].shape)
                    self.fillClusteredSamples(ordering,labels[ordering],sampids,None,clustring_method="DBSCAN")

    def fillClusteredSamples(self,ordered_indexes,cluster_labels,sampleids,reachability,clustring_method="OPTICS"):
        self.samplesTreeWidget.setColumnCount(3)
        # 设置头的标题
        self.samplesTreeWidget.setToolTip("Cluster ID = -1 means It is a noise sample")
        if clustring_method=="OPTICS":
            self.samplesTreeWidget.setHeaderLabels(['SampleId','Cluster ID','reachability'])
        elif clustring_method=="HDBSCAN":
            self.samplesTreeWidget.setHeaderLabels(['SampleId','Cluster ID','probability'])
        else: #DBSCAN
            self.samplesTreeWidget.setHeaderLabels(['SampleId','Cluster ID','-'])

        i=0
        for index in ordered_indexes:
            node = QTreeWidgetItem(self.samplesTreeWidget)
            node.setText(0, str(sampleids[index]))
            node.setText(1, str(cluster_labels[i]))
            if reachability is not None:
                node.setText(2, "{:.2f}".format(reachability[i]))
            i+=1
        #self.samplesTreeWidget.sortItems(2, Qt.DescendingOrder)
        self.samplesTreeWidget.resizeColumnToContents(0)


    def panToSampleCenter(self):
        item=self.samplesTreeWidget.currentItem()
        if item is None:
            item = self.samplesTreeWidget.topLevelItem(0)
        selSampleId=int(item.text(0))
        canvas_x0 = self.monitask.iface.mapCanvas().extent().xMinimum()
        canvas_y0 = self.monitask.iface.mapCanvas().extent().yMinimum()
        screen_res = self.monitask.iface.mapCanvas().mapUnitsPerPixel()
        for samp in self.filteredSamples:
            if samp[0]==selSampleId:
                self.monitask.iface.mapCanvas().setCenter(QgsPointXY(samp[3],samp[4]))
                self.monitask.iface.mapCanvas().refresh()
                self.panbackButton.setEnabled(True)
                self.monitask.iface.mapCanvas().scene().removeItem(self.monitask.canvasItem_Focus)
                #center=QgsPointXY((samp[3]-canvas_x0)/screen_res,(samp[4]-canvas_y0)/screen_res)
                center=QgsPointXY(samp[3],samp[4])
                #print_log(samp[3],samp[4],canvas_x0,canvas_y0,center.x(),center.y())
                self.monitask.canvasItem_Focus = FocusCanvasItem(self.monitask.iface.mapCanvas(),center)
                break

    def panBack(self):
        self.monitask.checktool.panBack()
        self.panbackButton.setEnabled(False)