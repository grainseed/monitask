# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings,QUrl,Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt import QtGui, QtWidgets, uic,QtNetwork
from qgis.core import QgsApplication,QgsUserProfileManager,QgsFieldProxyModel,QgsVectorLayer,QgsFields
from qgis.PyQt.QtWidgets import QMessageBox,QDialog
#from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


#from PyQt5 import *
import os
import getpass
from qgis.gui import QgsDataSourceSelectDialog
from .settings import SettingsClass
from .labelbase import LabelBase
from .utils import print_log


# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'settings_dialog.ui'))


class SettingsDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None,settingsObj=None):
        """Constructor."""
        super(SettingsDialog, self).__init__(parent)
        self.reply = None
        self.lb = None
        self.outlayerFields=[]
        if settingsObj is None:
            self.settingsObj=SettingsClass(os.path.dirname(__file__) + "\\monitask_config.ini", SettingsClass.IniFormat)
        else:
            self.settingsObj = settingsObj

        self.setupUi(self)
        self.accEdt.editingFinished.connect(self.checkUserProfile)
        self.submitBtnBox.accepted.connect(self.onAccepted)
        self.submitBtnBox.rejected.connect(self.onRejected)
        #self.submitBtnBox.clicked.connect(self.applySettings)
        self.newProfileCBox.toggled.connect(self.newProfileOnClick)
        self.imgSvrTest.clicked.connect(self.testImageServiceURL)
        self.tskSvrTest.clicked.connect(self.testTaskServiceURL)
        self.rstSvrTest.clicked.connect(self.testSubmitServiceURL)

        self.outlayer_fieldList.itemClicked.connect(self.outlayer_fieldListItemClicked)
        self.removeFieldButton.clicked.connect(self.removeSelectedField)
        self.addFiledButton.clicked.connect(self.addNewField)
        self.applyFieldButton.clicked.connect(self.applyChangeOnSelectedField)
        self.newFiledButton.clicked.connect(self.resetFieldWidget)

        self.newLB_Button.clicked.connect(self.newLabelBase)
        self.manLB_Button.clicked.connect(self.refineLabelBase)
        self.aboutLB_Button.clicked.connect(self.aboutLabelBase)

        self.browseDatasouceButton.clicked.connect(self.getFieldSrcLayerUri)
        self.metasrc_button.clicked.connect(self.getMetaSrcLayerUri)
        self.pos_index_button.clicked.connect(self.getNavSrcLayerUri)
        self.fieldTypeComboBox.currentTextChanged.connect(self.setFieldComboFilter)
        self.stopButton.clicked.connect(self.stopLblbaseRefine)
        self.resolutionUsedCombo.currentIndexChanged.connect(self.onResolutionSettingChanged)
        self.workDirWgt.fileChanged.connect(self.setLabelDefaultDir)

        self.loadSettings()

    def setLabelDefaultDir(self,workdir):
        self.labelDBFile.setDefaultRoot(workdir)

    def onResolutionSettingChanged(self,index):
        self.reslimit_label.setEnabled(index==1)
        self.minResolutionZoom.setEnabled(index==1)
        self.reslimit_to_label.setEnabled(index==1)
        self.maxResolutionZoom.setEnabled(index==1)


    # 发出下载请求
    def startRequest(self, url):
#        sslconfig=QtNetwork.QSslConfiguration()
#        sslconfig.setPeerVerifyMode(QtNetwork.QSslSocket.VerifyNone);
#        sslconfig.setProtocol(QtNetwork.QSsl.TlsV1_1);

        self.networkmanager = QtNetwork.QNetworkAccessManager()
        self.remarkEdt.append(str(url))
        request=QtNetwork.QNetworkRequest(url)
#        request.setSslConfiguration(sslconfig)
#        self.remarkEdt.append("sslConfiguration:"+str(request.sslConfiguration()))

        self.reply = self.networkmanager.get(request)
        self.networkmanager.finished.connect(self.httpFinished)
        self.networkmanager.sslErrors.connect(self.showSSLError)
#        self.reply.readyRead.connect(self.httpReadyRead)
#        self.reply.downloadProgress.connect(self.updateDataReadProgress)

    def showSSLError(self,reply,errors):
        self.remarkEdt.append("SSL Error:"+errors)

    def testImageServiceURL(self):
        self.remarkEdt.append(self.imgSvrEdt.text())
        self.startRequest(QUrl(self.imgSvrEdt.text()))

    def testTaskServiceURL(self):
        self.startRequest(QUrl(self.tskSvrEdt.text()))

    def testSubmitServiceURL(self):
        self.startRequest(QUrl(self.rstSvrEdt.text()))

    def httpFinished(self,reply):
        if reply.error():
            self.remarkEdt.append(reply.errorString())
        else:
            self.remarkEdt.append("httpFinished:" + str(reply.readAll(),'utf-8'))

    def httpReadyRead(self):
        pass
        self.remarkEdt.append("httpReadyRead:"+str(self.reply.readAll(),'utf-8'))

    def updateDataReadProgress(self, bytesRead, totalBytes):
        self.remarkEdt.append(str(bytesRead)+'/'+str(totalBytes)+'Bytes')


    def checkUserProfile(self):
        profMan=QgsUserProfileManager()
        a = profMan.allProfiles() #get all profiles in a list
        if not self.accEdt.text() in  a:
            self.newProfileCBox.setEnabled(True)
            self.infoEdt.setPlainText('There is not a user profile with the same name as your account name, if you want to create it, please check the following checkbox and apply')
        else:
            self.newProfileCBox.setEnabled(False)
            self.infoEdt.setPlainText('')
        # curprofile=profMan.userProfile()
        # self.infoEdt.appendPlainText(profMan.rootLocation())
        # if self.accEdt.text() != curprofile:
        #     self.infoEdt.appendPlainText("账号名称与当前的用户空间（User Profile）的名称"+curprofile+"不同，建议新建同名的用户空间，避免和其他用户的工作空间发生干扰，或使用当前用户空间的名称作为账号名称")

    def newProfileOnClick(self,isChecked):
        if isChecked:
            profileName = self.accEdt.text()
            if QgsUserProfileManager().profileExists(profileName):
                self.infoEdt.setPlainText("名称为"+profileName+" 的用户空间已经存在，不需新建。")
            else:
                self.infoEdt.setPlainText(
                    '将创建一个与您的账号名相同的新用户空间，并生成新的启动快捷方式，您需要使用该链接重新启动QGIS到您自己的用户空间。（注：该功能需要准确获得当前所用User Profile的名称，从而获得其所在的目录，才能在创建后迁移用户设置信息。目前由于QGIS bug，暂时未实现）')
        else:
            self.infoEdt.setPlainText('')

    def onRejected(self):
        self.close()

    def onAccepted(self):
        self.updateSettings()
        if self.newProfileCBox.isEnabled() and self.newProfileCBox.isChecked():
            self.createUserProfile(self.accEdt.text())
        msg = QMessageBox()
        msg.setWindowTitle("Message Box")
        msg.setText("Settings saved.")
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
        self.close()

    # 以下将创建一个新用户空间，并将当前用户空间的已有设置，包括本plugin迁移到其中，并生成新的启动快捷方式，用户需要使用该链接重新启动QGIS到您自己的用户空间。
    # （注：该功能需要准确获得当前所用User Profile的名称，从而获得其所在的目录，才能在创建后迁移用户设置信息。目前由于QGIS bug，暂时未实现）
    def createUserProfile(self,profileName):
        if QgsUserProfileManager().profileExists(profileName):
            pass
        else:
            self.infoEdt.setPlainText('将创建一个与您的账号名相同的新用户空间，并生成新的启动快捷方式，您需要使用该链接重新启动QGIS到您自己的用户空间。（注：该功能需要准确获得当前所用User Profile的名称，从而获得其所在的目录，才能在创建后迁移用户设置信息。目前由于QGIS bug，暂时未实现）')
        ##  todo：同时把本plugin拷贝安装到该用户空间，相关设置也拷贝到该用户空间，同时为该用户生成专门的程序快捷方式
        #   QgsUserProfileManager().createUserProfile(profileName) #create profile if doesn't exist
        #   QgsUserProfileManager(r).loadUserProfile(g) #then load it

    def loadSettings(self):
        def fillOutlayerAttributes(attributeSetings):
#            QMessageBox.warning(None, 'Warning', "Value:"+setValue)
            if attributeSetings:
                attributeSetings=eval(attributeSetings)
                if len(attributeSetings)>0:
                    self.outlayerFields=attributeSetings
                    self.outlayer_fieldList.clear()
                    for field in attributeSetings:
                        self.outlayer_fieldList.addItem(field[0])
                    self.outlayer_fieldList.setCurrentRow(0)
                    self.fieldNameEdit.setText(attributeSetings[0][0])
                    self.fieldTypeComboBox.setCurrentText(attributeSetings[0][1])
                    self.fieldLengthEdit.setText(str(attributeSetings[0][2]))

                    self.sourceFieldComboBox.setField(attributeSetings[0][4])
                    if attributeSetings[0][3].strip():
                        vlayer = QgsVectorLayer(attributeSetings[0][3])
                        if vlayer:
                            self.sourceFieldComboBox.setFields(vlayer.fields())
                            self.sourceFieldComboBox.setField(attributeSetings[0][4])
                    else:
                        self.sourceFieldComboBox.setFields(QgsFields())


                    self.fieldRoleComboBox.setCurrentText(attributeSetings[0][5])

        def fillUIelement(UIelement, setting_value, placeholderText):
            if setting_value:
                # print_log(UIelement.objectName(), setting_value)
                # if UIelement.objectName()=="maskColorButton":
                #     print_log(dir(UIelement),hasattr(UIelement,"setColor"))
                #print_log("setting_value:",setting_value,type(setting_value))
                if hasattr(UIelement,"setColor"):
                    #QMessageBox.warning(None, 'Warning',str(setting_value)+":"+QColor(setting_value).name())
                    UIelement.setColor(QColor(setting_value))
                elif hasattr(UIelement,"setFilePath"):
                    UIelement.setFilePath(setting_value)
                elif hasattr(UIelement,"setValue"):
                    UIelement.setValue(eval(str(setting_value)))
                elif hasattr(UIelement, "setCurrentIndex"):
                    try:
                        UIelement.setCurrentIndex(int(setting_value))
                    except:
                        UIelement.setCurrentText(str(setting_value))
                elif hasattr(UIelement, "setChecked"):

                    UIelement.setChecked(str(setting_value).upper() == "TRUE")
                elif hasattr(UIelement, "setText"):
                    UIelement.setText(setting_value)
            if placeholderText:
                UIelement.setPlaceholderText(placeholderText)

        fillUIelement(self.labelDBFile, self.settingsObj.General_labelDBFile, None)
        fillUIelement(self.img_meta_source, self.settingsObj.General_img_meta_source, None)
        fillUIelement(self.pos_index_source, self.settingsObj.General_pos_index_source, None)

        fillUIelement(self.autoNewOutLayerCheckBox, self.settingsObj.General_autoNewOutLayer, None)
        fillUIelement(self.parcelMinArea, self.settingsObj.General_parcelMinArea, None)
        fillUIelement(self.outFileNameEdit, self.settingsObj.General_outFileName, None)
        fillUIelement(self.outlayerNameEdit, self.settingsObj.General_outlayerName, None)
        fillUIelement(self.changeDetectedEdit, self.settingsObj.General_changeDetectedlayerName, None)
        fillUIelement(self.outFileFormatComboBox, self.settingsObj.General_outFileFormat, None)

        if self.settingsObj.General_outLayerFields is None:
            self.settingsObj.General_outLayerFields="[('labelid', 'String', '', '', '', 'Labeling')]"

        fillOutlayerAttributes(self.settingsObj.General_outLayerFields)

        fillUIelement(self.resolutionUsedCombo, self.settingsObj.General_resolutionUsed, None)
        fillUIelement(self.minResolutionZoom, self.settingsObj.General_minResolutionZoom, None)
        fillUIelement(self.maxResolutionZoom, self.settingsObj.General_maxResolutionZoom, None)

        fillUIelement(self.nameEdt, self.settingsObj.User_username, "Please set your name")
        fillUIelement(self.accEdt, self.settingsObj.User_accname, "Please set your account name")
        fillUIelement(self.pswEdt, self.settingsObj.User_password, "Please set your password")
        fillUIelement(self.orgEdt, self.settingsObj.User_orgname, "Please set full name of your organization")
        if self.settingsObj.User_workingdir:
            self.workDirWgt.setFilePath(self.settingsObj.User_workingdir)
        else:
            prefixpath=QgsApplication.prefixPath()
            workdir=prefixpath[0:prefixpath.find("qgis")]
            if os.path.exists(workdir):
                workdir=workdir+"work"
            else:
                drive,dir=os.path.splitdrive()
                dir=dir.split("/")
                workdir=drive+"/"+dir[1]+"/work"
            if not os.path.exists(workdir):
                os.makedirs(workdir)
            self.workDirWgt.setFilePath(workdir)
            self.settingsObj.User_workingdir=workdir

        roleidx=self.settingsObj.User_workrole
        if roleidx:
            self.roleCBox.setCurrentIndex(int(roleidx))
        else:
            self.roleCBox.setCurrentIndex(-1)

        fillUIelement(self.imgSvrEdt, self.settingsObj.NetService_image_service_url, "Please set URL of the image service")
        fillUIelement(self.tskSvrEdt, self.settingsObj.NetService_task_service_url, "Please set URL of the task service")
        fillUIelement(self.rstSvrEdt, self.settingsObj.NetService_result_service_url, "Please set URL of the result upload service")

        fillUIelement(self.maskColorButton, self.settingsObj.Advanced_mask_color, None)
        fillUIelement(self.maskOpacitySpin, self.settingsObj.Advanced_mask_opacity, None)
        fillUIelement(self.denoise_kernel_size_spinbox, self.settingsObj.Advanced_denoise_kernel_size, None)
        fillUIelement(self.padding_spinbox, self.settingsObj.Advanced_padding, None)
        fillUIelement(self.expand_pixel_spinbox, self.settingsObj.Advanced_expand_pixel, None)
        fillUIelement(self.shrink_pixels_spinbox, self.settingsObj.Advanced_shrink_pixels, None)
        fillUIelement(self.simplify_method_ComboBox, self.settingsObj.Advanced_simplify_method, None)
        fillUIelement(self.simplify_torlerance_spinbox, self.settingsObj.Advanced_simplify_torlerance, None)
        fillUIelement(self.simplify_keep_topo_checkbox, self.settingsObj.Advanced_simplify_keep_topo, None)
        fillUIelement(self.snap2grid_hspace_spinbox, self.settingsObj.Advanced_snap2grid_hspace, None)
        fillUIelement(self.snap2grid_vspace_spinbox, self.settingsObj.Advanced_snap2grid_vspace, None)
        fillUIelement(self.smooth_iterations_spinbox, self.settingsObj.Advanced_smooth_iterations, None)
        fillUIelement(self.smooth_offset_spinbox, self.settingsObj.Advanced_smooth_offset, None)
        fillUIelement(self.smooth_minDist_spinbox, self.settingsObj.Advanced_smooth_minDist, None)
        fillUIelement(self.smooth_maxAngle_spinbox, self.settingsObj.Advanced_smooth_maxAngle, None)
        fillUIelement(self.ortho_torlerance_spinbox, self.settingsObj.Advanced_ortho_torlerance, None)
        fillUIelement(self.ortho_maxiteration_spinbox, self.settingsObj.Advanced_ortho_maxiteration, None)
        fillUIelement(self.ortho_angleThreshold_spinbox, self.settingsObj.Advanced_ortho_angleThreshold, None)
        fillUIelement(self.cd_model_file, self.settingsObj.Advanced_cd_model_file, None)
        fillUIelement(self.cd_modelFormat_comboBox, self.settingsObj.Advanced_cd_modelFormat, None)

#        self.getUserProfiles()

    def updateSettings(self):
        #QMessageBox.warning(None, 'Warning','Applied')
        self.settingsObj.General_labelDBFile=self.labelDBFile.filePath()
        self.settingsObj.General_img_meta_source=self.img_meta_source.text()
        self.settingsObj.General_pos_index_source=self.pos_index_source.text()

        self.settingsObj.General_autoNewOutLayer=self.autoNewOutLayerCheckBox.isChecked()
        self.settingsObj.General_parcelMinArea=self.parcelMinArea.text()
        self.settingsObj.General_outFileName=self.outFileNameEdit.text()
        self.settingsObj.General_outlayerName=self.outlayerNameEdit.text()
        self.settingsObj.General_changeDetectedlayerName=self.changeDetectedEdit.text()
        self.settingsObj.General_outFileFormat=self.outFileFormatComboBox.currentText()

        self.settingsObj.General_outLayerFields=str(self.outlayerFields) if len(self.outlayerFields)>0  else "[('labelid', 'String', '', '', '', 'Labeling')]"

        self.settingsObj.General_resolutionUsed=self.resolutionUsedCombo.currentIndex()
        self.settingsObj.General_minResolutionZoom=self.minResolutionZoom.value()
        self.settingsObj.General_maxResolutionZoom=self.maxResolutionZoom.value()

        self.settingsObj.User_username=self.nameEdt.text()
        self.settingsObj.User_accname=self.accEdt.text()
        self.settingsObj.User_password=self.pswEdt.text()
        self.settingsObj.User_orgname=self.orgEdt.text()
        self.settingsObj.User_workingdir=self.workDirWgt.filePath()
        self.settingsObj.User_workrole=self.roleCBox.currentIndex()

        self.settingsObj.NetService_image_service_url=self.imgSvrEdt.text()
        self.settingsObj.NetService_task_service_url=self.tskSvrEdt.text()
        self.settingsObj.NetService_result_service_url=self.rstSvrEdt.text()

        self.settingsObj.Advanced_mask_color=self.maskColorButton.color().name()
        self.settingsObj.Advanced_mask_opacity=self.maskOpacitySpin.value()
        self.settingsObj.Advanced_denoise_kernel_size=self.denoise_kernel_size_spinbox.value()
        self.settingsObj.Advanced_padding=self.padding_spinbox.value()
        self.settingsObj.Advanced_expand_pixel=self.expand_pixel_spinbox.value()
        self.settingsObj.Advanced_shrink_pixels=self.shrink_pixels_spinbox.value()
        self.settingsObj.Advanced_simplify_method=self.simplify_method_ComboBox.currentText()
        self.settingsObj.Advanced_simplify_torlerance=self.simplify_torlerance_spinbox.value()
        self.settingsObj.Advanced_simplify_keep_topo=self.simplify_keep_topo_checkbox.isChecked()
        self.settingsObj.Advanced_snap2grid_hspace=self.snap2grid_hspace_spinbox.value()
        self.settingsObj.Advanced_snap2grid_vspace=self.snap2grid_vspace_spinbox.value()
        self.settingsObj.Advanced_smooth_iterations=self.smooth_iterations_spinbox.value()
        self.settingsObj.Advanced_smooth_offset=self.smooth_offset_spinbox.value()
        self.settingsObj.Advanced_smooth_minDist=self.smooth_minDist_spinbox.value()
        self.settingsObj.Advanced_smooth_maxAngle=self.smooth_maxAngle_spinbox.value()
        self.settingsObj.Advanced_ortho_torlerance=self.ortho_torlerance_spinbox.value()
        self.settingsObj.Advanced_ortho_maxiteration=self.ortho_maxiteration_spinbox.value()
        self.settingsObj.Advanced_ortho_angleThreshold=self.ortho_angleThreshold_spinbox.value()
        self.settingsObj.Advanced_cd_model_file=self.cd_model_file.filePath()
        self.settingsObj.Advanced_cd_modelFormat=self.cd_modelFormat_comboBox.currentText()

        self.settingsObj.sync()

    def getFieldSrcLayerUri(self):
        uriObj=self.select_datasource()
        if uriObj is not None:
            self.srcLayerURIEdit.setText(uriObj.uri)
            vlayer=uriObj.vectorLayer("Error when get vector layer object")[0]
            if vlayer:
                self.sourceFieldComboBox.setLayer(vlayer)
                #print_log(vlayer.id(), vlayer.name(), vlayer.error())

    def setFieldComboFilter(self,current_text):
        fldType=self.fieldTypeComboBox.currentText()
        if fldType=="String":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.String)
        elif fldType== "Integer":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.Int|QgsFieldProxyModel.LongLong)
        elif fldType== "Double":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.Double)
        elif fldType== "Date":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.Date)
        elif fldType== "DateTime":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.DateTime)
        elif fldType== "Boolean":
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.Int)
        else:
            self.sourceFieldComboBox.setFilters(QgsFieldProxyModel.AllTypes)


    def getMetaSrcLayerUri(self):
        uriObj = self.select_datasource()
        if uriObj:
            self.img_meta_source.setText(uriObj.uri)

    def getNavSrcLayerUri(self):
        uriObj = self.select_datasource()
        if uriObj:
            self.pos_index_source.setText(uriObj.uri)

    def outlayer_fieldListItemClicked(self,item):
        index=self.outlayer_fieldList.currentRow()
        setValue=self.outlayerFields[index]
        self.fieldNameEdit.setText(setValue[0])
        self.fieldTypeComboBox.setCurrentText(setValue[1])
        self.fieldLengthEdit.setText(str(setValue[2]))
        self.srcLayerURIEdit.setText(setValue[3])
        if setValue[3].strip():
            vlayer=QgsVectorLayer(setValue[3])
            if vlayer:
                self.sourceFieldComboBox.setFields(vlayer.fields())
                self.sourceFieldComboBox.setField(setValue[4])
        else:
            self.sourceFieldComboBox.setFields(QgsFields())

        self.fieldRoleComboBox.setCurrentText(setValue[5])


    def removeSelectedField(self):
        if self.outlayer_fieldList.currentRow()>-1:
            field_name=self.outlayer_fieldList.item(self.outlayer_fieldList.currentRow()).text()
            for i in range(len(self.outlayerFields),0,-1):
                if self.outlayerFields[i-1][0]==field_name:
                    self.outlayerFields.pop(i-1)
            self.outlayer_fieldList.takeItem(self.outlayer_fieldList.currentRow())

    def applyChangeOnSelectedField(self):
        if self.outlayer_fieldList.currentRow()>-1:
            field_name=self.outlayer_fieldList.item(self.outlayer_fieldList.currentRow()).text()
            chengedFieldName = self.fieldNameEdit.text().strip()
            if len(self.outlayer_fieldList.findItems(chengedFieldName, Qt.MatchExactly))>1:
                QMessageBox.warning(None, 'Warning',"修改后的字段和已有字段不能重名")
                return

            for i in range(len(self.outlayerFields),0,-1):
                if self.outlayerFields[i-1][0]==field_name:
                    changedField = (chengedFieldName,
                                self.fieldTypeComboBox.currentText(),
                                self.fieldLengthEdit.text(),
                                self.srcLayerURIEdit.text(),
                                self.sourceFieldComboBox.currentText(),
                                self.fieldRoleComboBox.currentText())

                    self.outlayerFields[i-1]=changedField
            self.outlayer_fieldList.item(self.outlayer_fieldList.currentRow()).setText(self.fieldNameEdit.text())
            self.updateSettings()

    def resetFieldWidget(self):
        self.fieldNameEdit.clear()
        self.fieldLengthEdit.clear()
        self.srcLayerURIEdit.setText("")
        self.sourceFieldComboBox.clear()
        self.fieldRoleComboBox.setCurrentText("Other")


    def addNewField(self):
        newFieldName=self.fieldNameEdit.text().strip()
        #不能重名
        if newFieldName:
            if len(self.outlayer_fieldList.findItems(newFieldName, Qt.MatchExactly))<1:
                self.outlayer_fieldList.addItem(newFieldName)
                newField=(newFieldName,
                          self.fieldTypeComboBox.currentText(),
                          self.fieldLengthEdit.text(),
                          self.srcLayerURIEdit.text(),
                          self.sourceFieldComboBox.currentText(),
                          self.fieldRoleComboBox.currentText())
                self.outlayerFields.append(newField)
                self.updateSettings()
            else:
                QMessageBox.warning(None, 'Warning',"新增字段和已有字段不能重名")


    def getUserProfiles(self):
        defaultsti = QgsApplication.qgisSettingsDirPath() #path to profiles
        os.chdir(defaultsti)
        os.chdir(os.path.dirname(os.getcwd()))
        r = os.getcwd()
        profMan=QgsUserProfileManager(r)
        self.infoEdt.appendPlainText("profile root:"+profMan.rootLocation())
        self.infoEdt.appendPlainText("default profile:"+profMan.defaultProfileName())

        a = profMan.allProfiles() #get all profiles in a list
        self.infoEdt.appendPlainText("All profiles:"+'\n'.join(a))

        g = getpass.getuser()  #登录操作系统的当前用户名称
        activeProfile=profMan.userProfile()

        #.settingsMenu().activeAction().text


        if activeProfile and activeProfile.name() != g:
            self.remarkEdt.setText(profMan.userProfile().name()+';You''d better use create your own user profile with name as '+g)

    def newLabelBase(self):
        lb_file=self.labelDBFile.lineEdit().value().strip()
        msg = QMessageBox()
        msg.setWindowTitle("Message Box")
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok)
        if not lb_file:
            lb_file=os.path.join(self.labelDBFile.defaultRoot(),"new_label_sys.db")
            self.labelDBFile.setFilePath(lb_file)
            msg.setText("Please specify the full path of SQLite database file with extension '*.db' or rename the default name as you want")
            msg.exec_()
            return
        if os.path.exists(lb_file):
            msg.setText("The label database file is already exist. If you want to make a new one, please change the file name and click NEW button again.")
            msg.exec_()
        else:
            lb=LabelBase(lb_file)
            lb.logMetaInfo(self.settingsObj.User_username,self.settingsObj.User_orgname,self.ls_descEdit.toPlainText())
            msg.setText("the specified new label database has been initiated.")
            msg.exec_()

    def aboutLabelBase(self):
        lb_file=self.labelDBFile.lineEdit().value().strip()
        if lb_file:
            if os.path.exists(lb_file):
                msg = QMessageBox()
                msg.setWindowTitle("Message Box")
                lb = LabelBase(lb_file)
                guid,author,org,desc,created,updated=tuple(lb.getMetaInfo())
                msg.setText("The label system (GUID:{}) is created by {}, from {} on {}, latest update on {}.".format(guid,author,org,created,updated))
                msg.setIcon(QMessageBox.Information)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
                del lb

    def refineLabelBase(self):
        lb_file = self.labelDBFile.lineEdit().value().strip()
        self.lb = LabelBase(lb_file)
        self.lb.refresh_pca_agents_of_alllabels(progress_bar=self.progressBar,min_usedtimes=1,close_connect=True)
        self.lb.update_sim_with_eachother(overwrite=True,progress_bar=self.progressBar,close_connect=True,skipExisting=True)

    def stopLblbaseRefine(self):
        self.lb.setInterruptLongTransaction(True)

    def select_datasource(self):
        ds_select_dialog = QgsDataSourceSelectDialog(parent=self)
        ds_select_dialog.resize(600, 400)
        ds_select_dialog.showFilterWidget(True)
        if ds_select_dialog.exec_()==QDialog.Accepted:
            uriObj=ds_select_dialog.uri()
            #print_log(uriObj.uri,uriObj.filePath,uriObj.isValid(),uriObj.layerId,uriObj.layerType,uriObj.name)
            return uriObj
        else:
            return None

    def focusOnLabelbase(self):
        self.newLB_Button.setFocus()

