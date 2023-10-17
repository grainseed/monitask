from .utils import getLayerByTile,isOutputLayerValid

layers_dict={"baseimg_layer":None,
            "output_layer":None,
            "crs":None,
            "extent_layer":None,
            "mask_layer":None,
            "temp_vector_layer":None}

class proxyClass(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

class  WorkingLayers:
    def __int__(self):
        #wl = proxyClass(layers_dict)
        self.baseimg_layer = None
        self.output_layer = None
        self.previmg_layer = None
        self.crs=""
        self.extent_layer=None
        self.mask_layer=None
        self.temp_vector_layer=None
        self.navi_layer=None
        self.changedetected_layer=None

    def __int__(self, baseimg_layer_name, output_layer_name):
        self.baseimg_layer = None
        if baseimg_layer_name is None:
            self.baseimg_layer = None
        else:
            self.baseimg_layer=getLayerByTile(baseimg_layer_name)

        if output_layer_name is None:
            self.output_layer = None
        else:
            self.output_layer=getLayerByTile(output_layer_name)

        if  self.baseimg_layer:
            self.crs=self.baseimg_layer.crs()
        else:
            self.crs=None

        self.extent_layer=None
        self.mask_layer=None
        self.temp_vector_layer=None
        self.navi_layer=None
        self.previmg_layer = None
        self.changedetected_layer=None


    def updateCRS(self):
        if  self.baseimg_layer:
            self.crs=self.baseimg_layer.crs()
        else:
            self.crs=None

    def setBaseImageLayer(self,base_image_layer):
        '''
        param: base_image_layer,图层名称或QgsRasterLayer对象
        '''
        if type(base_image_layer) is str:
            self.baseimg_layer = getLayerByTile(base_image_layer)
        else:
            self.baseimg_layer = base_image_layer
        self.updateCRS()

    def setPrevImageLayer(self,prev_image_layer):
        '''
        param: prev_image_layer,图层名称或QgsRasterLayer对象
        '''
        if type(prev_image_layer) is str:
            self.previmg_layer = getLayerByTile(prev_image_layer)
        else:
            self.previmg_layer = prev_image_layer

    def setCDLayer(self,cd_layer):
        if type(cd_layer) is str:
            self.changedetected_layer = getLayerByTile(cd_layer)
        else:
            self.changedetected_layer = cd_layer


    def setOutputLayer(self,output_layer):
        '''
        param: output_layer,图层名称或QgsVectorLayer对象
        '''
        if type(output_layer) is str:
            self.output_layer = getLayerByTile(output_layer)
        else:
            self.output_layer=output_layer


    def setExtentLayer(self,extent_layer):
        self.extent_layer=extent_layer

    def setMaskLayer(self,mask_layer):
        self.mask_layer=mask_layer

    def setTempVectorLayer(self,temp_vector_layer):
        self.temp_vector_layer=temp_vector_layer

    def setNaviLayer(self,navi_layer):
        self.navi_layer=navi_layer


    def isReady(self, settingsObj):
        '''
        判断关键图层是否具备，可以进行工作
        '''
        #print_log(self.output_layer.name())
        ready = self.baseimg_layer is not None
        ready &= (getLayerByTile(self.baseimg_layer.name()) is not None)
        ready &= self.output_layer is not None
        ready &= (getLayerByTile(self.output_layer.name()) is not None)
        ready &= self.output_layer.crs()==self.baseimg_layer.crs()
        if ready:
            ready = isOutputLayerValid(self.output_layer,settingsObj)
        if ready: self.updateCRS()
        return ready

    def tidy(self):
        '''清理掉依赖在窗口中不再存在的图层'''
        if getLayerByTile(self.output_layer.name()) is None:
            self.output_layer=None

        if getLayerByTile(self.baseimg_layer.name()) is None:
            self.baseimg_layer=None
            self.crs=None
    def print_me(self,context):
        try:
            print_log(context)
            if hasattr(self,"baseimg_layer"): print_log("---WL.baseimg_layer:",self.baseimg_layer)
            if hasattr(self,"output_layer"): print_log("---WL.output_layer:",self.output_layer)
            if hasattr(self,"crs"): print_log("---WL.crs",self.crs)
            if hasattr(self,"extent_layer"): print_log("---WL.extent_layer",self.extent_layer)
            if hasattr(self,"mask_layer"): print_log("---WL.mask_layer",self.mask_layer)
            if hasattr(self,"temp_vector_layer"):print_log("---WL.temp_vector_layer",self.temp_vector_layer)
        except:
            pass


