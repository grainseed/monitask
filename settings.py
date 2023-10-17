from qgis.PyQt.QtCore import QSettings
'''
QSettings的继承类，便于将key作为对象的属性进行读写访问
'''
class SettingsClass(QSettings):
    def __getattr__(self, key):
        v=self.value("MoniTask/"+key)
        if type(v)==str and v.replace(".", "").replace("-", "").isdigit():
            v=eval(v)
        return v

    def __setattr__(self, key,value):
        self.setValue("MoniTask/"+key,value)
        
    def reload(self):
        self.sync()



'''
setObj=SettingsClass("ini fiel path",QSettings.IniFormat)
'''