import os,sqlite3,cv2
import numpy as np
import uuid
from qgis.PyQt.QtWidgets import QApplication

from .utils import cosine_similarity,correlation_coefficient,mutual_info,print_log

class LabelItem:
    def __init__(self,title,id,superid,cc,desc,rules):
        self.title=title
        self.id=id
        self.superid=superid
        self.cc=cc
        self.desc=desc
        self.reshape_rule=rules


class LabelSample:
    def __init__(self,labelid=-1,samp_img=None,gebd=None,lebd=None):
        self.labelid=labelid
        self.samp_img = samp_img
        self.gebd=gebd
        self.lebd1=lebd

    def set_id(self,fid):
        self.fid=fid

    def set_histogram(self,ghis,lhis):
        #print_log("Befor set Hist：",ghis.dtype,lhis.dtype)
        self.ghis=ghis
        self.lhis=lhis

    def set_source(self,src_layer,src_featid):
        self.src_layer=src_layer
        self.src_featid=src_featid

    def set_sizeinfo(self,mask_sizex,mask_sizey,samp_len):
        self.samp_len=samp_len
        self.mask_sizex=mask_sizex
        self.mask_sizey=mask_sizey

    def set_entropy(self,samp_entropy,parcel_entropy):
        self.samp_entropy=samp_entropy
        self.parcel_entropy=parcel_entropy

    def set_position(self,longitude,latitude):
        self.longitude=longitude
        self.latitude=latitude

    def set_simpca(self,gsim_pca,lsim_pca):
        self.gsim_pca=gsim_pca
        self.lsim_pca=lsim_pca

    def set_image_meta(self,img_date,img_resolution,img_platform,samp_resolution):
        self.img_date=img_date
        self.img_resolution=img_resolution
        self.img_platform=img_platform
        self.samp_resolution=samp_resolution

    def set_selfsim(self,glsim,glhissim):
        self.glsim=glsim
        self.glhissim=glhissim

class LabelBase(object):
    def __init__(self,baseFile):
        self.baseFile=baseFile
        self.connection=None
        self.labelItems=[]
        self.guid=None
        self.interruptLongTransaction=False
        if baseFile is not None and baseFile.strip()!='':
            if not os.path.exists(baseFile):
                self.initLabelBase(baseFile)
            else:
                self.getLabelItems()

    def __del__(self):
        self.close()

    def initLabelBase(self,filepath):
        self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute('''CREATE TABLE meta(
                                fid integer PRIMARY KEY AUTOINCREMENT,
                                guid varchar(64)  NOT NULL,
                                author character(16),
                                org varchar(128),
                                desc varchar(255),
                                created datetime DEFAULT CURRENT_TIMESTAMP,
                                updated datetime DEFAULT CURRENT_TIMESTAMP
                            )''')
            self.connection.commit()
            cursor.execute('''CREATE TABLE labels(
                                fid integer PRIMARY KEY AUTOINCREMENT,
                                superid integer DEFAULT -1,
                                title varchar(64)  NOT NULL,
                                description varchar(255),
                                reshape_rule varchar(255) DEFAULT "SimplifyPreserveTopology",
                                cc character(10),
                                used_times integer DEFAULT 0,
                                created datetime DEFAULT CURRENT_TIMESTAMP,
                                updated datetime DEFAULT CURRENT_TIMESTAMP
                            )''')
            self.connection.commit()
            cursor.execute('''CREATE TABLE samples(
                                fid integer PRIMARY KEY AUTOINCREMENT,
                                labelid integer NOT NULL,
                                src_layer varchar(64),
                                src_featid integer,
                                gebd Blob,
                                lebd1 Blob,
                                lebd2 Blob,
                                ghis Blob,
                                lhis Blob,
                                mask_sizex integer,
                                mask_sizey integer,
                                samp_img Blob,
                                samp_len integer,
                                img_date Date,
                                img_resolution Real,
                                img_platform character(10),
                                samp_resolution Real,
                                samp_entropy Real,
                                parcel_entropy Real,
                                gsim_pca Real DEFAULT 0,
                                lsim_pca Real DEFAULT 0,
                                glsim Real DEFAULT 0, 
                                glhissim Real DEFAULT 0,
                                latitude Real,
                                longitude Real,
                                gsim_agents Real DEFAULT 0,
                                lsim_agents Real DEFAULT 0,
                                catch_on datetime DEFAULT CURRENT_TIMESTAMP
                            )''')
            self.connection.commit()
            cursor.execute('''CREATE TABLE ebdpca(
                                fid integer PRIMARY KEY AUTOINCREMENT,
                                labelid integer NOT NULL,
                                gpca Blob,
                                lpca Blob,
                                gscore Real,
                                lscore Real,
                                resolution Real,
                                extent character(128),
                                gagents Blob,
                                lagents Blob,
                                gagent_count smallint,
                                lagent_count smallint
                            )''')
            self.connection.commit()
            cursor.execute('''CREATE TABLE similarity(
                                fid integer PRIMARY KEY AUTOINCREMENT,
                                fromsampid integer NOT NULL,
                                withsampid integer NOT NULL,
                                ggsim Real DEFAULT 0,
                                glsim Real DEFAULT 0,
                                llsim Real DEFAULT 0,
                                lgsim Real DEFAULT 0,
                                ggcorrcoef Real DEFAULT 0,
                                glcorrcoef Real DEFAULT 0,
                                llcorrcoef Real DEFAULT 0,
                                lgcorrcoef Real DEFAULT 0,
                                mutualinfo Real DEFAULT 0,
                                gghissim Real DEFAULT 0,
                                glhissim Real DEFAULT 0,
                                llhissim Real DEFAULT 0,
                                lghissim Real DEFAULT 0
                            )''')
            self.connection.commit()
            cursor.execute('''create view samp_sim AS
                            select distinct fromsample.*,withsample.*,ggsim,glsim,llsim,lgsim,ggcorrcoef, glcorrcoef,llcorrcoef,lgcorrcoef,mutualinfo
                            from (
                                select samples.fid as fromsampid,labels.title as fromtitle,samples.mask_sizex as fromx,
                                samples.mask_sizey as fromy,samples.samp_len as fromlen,glsim as fromselfsim,samp_entropy as from_entropy
                                from labels,samples
                                where labels.fid=samples.labelid
                            ) as fromsample,
                            (
                                select samples.fid as withsampid,labels.title as withtitle,samples.mask_sizex as withx,
                                samples.mask_sizey as withy,samples.samp_len as withlen,glsim as withlfsim,samp_entropy as with_entropy
                                from labels,samples
                                where labels.fid=samples.labelid
                            ) as withsample,
                            similarity
                            where similarity.fromsampid=fromsample.fromsampid and similarity.withsampid=withsample.withsampid
                            order by llsim desc,fromtitle,fromsampid,withtitle,withsampid
                        ''')
            self.connection.commit()
            cursor.close()
        except Exception as e:
            print_log(e)
            print_log("Create table failed")
        finally:
            self.connection.close()

    def connect(self):
        if not self.is_connected():
#            if os.path.exists(self.baseFile):
            if self.baseFile is not None and self.baseFile.strip()!="":
                self.connection= sqlite3.connect(self.baseFile)
                return True
            else:
                self.connection=None
                return False
        else:
            return True

    def close(self):
        if  self.connection:
            self.connection.close()

    def is_connected(self):
        try:
            if self.connection:
                self.connection.execute("SELECT * FROM labels LIMIT 1")
                return True
            else:
                return False
        except sqlite3.ProgrammingError as e:
            return False

    def logMetaInfo(self,author,org,description="",close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select updated from labels order by updated DESC limit 1")
        updateTime = lblcur.fetchone()
        lblcur.execute("select guid from meta")
        guid = lblcur.fetchone()
        if guid:
            self.guid=guid[0]
            if updateTime:
                if description:
                    sql ="update meta set author='{}',org='{}',desc='{}',updated='{}'".format(author, org,description,updateTime[0])
                else:
                    sql ="update meta set author='{}',org='{}',updated='{}'".format(author, org,updateTime[0])
            else:
                if description:
                    sql = "update meta set author='{}',org='{}',desc='{}'".format(author, org,description)
                else:
                    sql = "update meta set author='{}',org='{}'".format(author, org)

            lblcur.execute(sql)
        else:
            self.guid=str(uuid.uuid1())
            lblcur.execute("insert into meta(guid,author,org,desc) values(?,?,?,?)", (self.guid, author, org,description))

        self.connection.commit()
        lblcur.close()
        if close_connect:
            self.close()


    def updateMetaTime(self,close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select updated from labels order by updated DESC limit 1")
        updateTime = lblcur.fetchone()[0]
        if updateTime:
            lblcur.execute("update meta set updated='{}'".formate(updateTime))
            self.connection.commit()
        lblcur.close()
        if close_connect:
            self.close()

    def getMetaInfo(self,close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select guid,author,org,desc,created,updated from meta")
        meta = lblcur.fetchone()
        lblcur.close()
        if close_connect:
            self.close()
        if meta:
            self.guid=meta[0]
        else:
            self.guid=None
        return meta


    def getLabelItems(self,close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select title,fid,superid,cc,description,reshape_rule from labels")
        labels = lblcur.fetchall()
        lblcur.close()
        self.labelItems.clear()
        for label in labels:
            rules=label[5].split(",") if label[5] else []
            self.labelItems.append(LabelItem(label[0], label[1], label[2], label[3], label[4],rules))
        if close_connect:
            self.close()

    def getLabelItemById(self,id):
        for item in self.labelItems:
            if item.id==id:
                return item
        return None

    def incedentLabelUsedTimes(self,id,times=1,close_connect=True):
        try:
            #print_log("update labels set used_times= used_times+{} where fid={}".format(times,id))
            if not self.connect(): return
            lblcur = self.connection.cursor()
            lblcur.execute("update labels set used_times= used_times+{} where fid={}".format(times,id))
            self.connection.commit()
        except sqlite3.Error as error:
            print_log("Failed to update used_times.", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def getLabelItemByTitle(self,title):
        for item in self.labelItems:
            if item.title==title:
                return item
        return None

    def getLabelSamplesByLabelId(self,labelid,limit=5,close_connect=True):
        if not self.connect(): return
        labelSamples=[]
        lblcur = self.connection.cursor()
        sql="select fid,gebd,lebd1,samp_img,samp_entropy,longitude,latitude from samples where labelid={}".format(labelid)
        sql=sql + " order by random()"
        if limit>0:
            sql = sql + " limit "+str(limit)
        #print_log(sql)
        lblcur.execute(sql)
        samples = lblcur.fetchall()
        lblcur.close()
        for sample in samples:
            labelSample=LabelSample()
            labelSample.labelid=labelid
            labelSample.id=sample[0]
            labelSample.gebd =np.frombuffer(sample[1],dtype=np.float32).reshape((1, -1))
            labelSample.lebd1=np.frombuffer(sample[2],dtype=np.float32).reshape((1, -1))
            #labelSample.lebd2=np.frombuffer(sample[3],dtype=np.float32).reshape((1, -1))
            labelSample.samp_img= cv2.imdecode(np.frombuffer(sample[3],dtype=np.uint8),cv2.IMREAD_COLOR)
            labelSample.samp_entropy = sample[4]
            labelSample.longitude = sample[5]
            labelSample.latitude = sample[6]
            labelSamples.append(labelSample)
        if close_connect:
            self.close()
        return labelSamples

    def getLabelSampleById(self,sampleid,close_connect=True):
        if not self.connect(): return None
        lblcur = self.connection.cursor()
        sql="select fid,labelid,gebd,lebd1,samp_img,ghis,lhis,samp_entropy from samples where fid={}".format(sampleid)
        lblcur.execute(sql)
        sample = lblcur.fetchone()
        lblcur.close()
        labelSample=LabelSample()
        labelSample.id=sample[0]
        labelSample.labelid = sample[1]
        labelSample.gebd =np.frombuffer(sample[2],dtype=np.float32).reshape((1, -1))
        labelSample.lebd1=np.frombuffer(sample[3],dtype=np.float32).reshape((1, -1))
        #labelSample.lebd2=np.frombuffer(sample[3],dtype=np.float32).reshape((1, -1))
        labelSample.samp_img= cv2.imdecode(np.frombuffer(sample[4],dtype=np.uint8),cv2.IMREAD_COLOR)
        labelSample.ghis =np.frombuffer(sample[5],dtype=np.single).reshape(-1)
        labelSample.lhis=np.frombuffer(sample[6],dtype=np.single).reshape(-1)
        labelSample.samp_entropy = sample[7]
        if close_connect:
            self.close()
        return labelSample
    def getLabelSampleByLayerAndFeatid(self,layername,featid,close_connect=True):
        if not self.connect(): return None
        lblcur = self.connection.cursor()
        sql="select fid,labelid,gebd,lebd1,samp_img,ghis,lhis,samp_entropy,longitude,latitude from samples where src_layer='{}' and src_featid={}".format(layername,featid)
        lblcur.execute(sql)
        sample = lblcur.fetchone()
        lblcur.close()
        if sample:
            labelSample=LabelSample()
            labelSample.id=sample[0]
            labelSample.labelid = sample[1]
            labelSample.gebd =np.frombuffer(sample[2],dtype=np.float32).reshape((1, -1))
            labelSample.lebd1=np.frombuffer(sample[3],dtype=np.float32).reshape((1, -1))
            #labelSample.lebd2=np.frombuffer(sample[3],dtype=np.float32).reshape((1, -1))
            labelSample.samp_img= cv2.imdecode(np.frombuffer(sample[4],dtype=np.uint8),cv2.IMREAD_COLOR)
            labelSample.ghis =np.frombuffer(sample[5],dtype=np.single).reshape(-1)
            labelSample.lhis=np.frombuffer(sample[6],dtype=np.single).reshape(-1)
            labelSample.samp_entropy = sample[7]
            labelSample.longitude = sample[8]
            labelSample.latitude = sample[9]
            if close_connect:
                self.close()
            return labelSample
        else:
            return None

    def getOddSamplesOfLabel(self,layername,sampleid,labelid,sim_threshhold,close_connect=True):
        '''
        获取与指定sample同一label但相似性低于sim_threshhold的其他从layername中获取的samples
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        #sql="select withsampid,llsim, from similarity where fromsampid={}".format(sampleid)
        sql="select withsampid as sampid,labelid,llsim,longitude,latitude from similarity,samples\
         where fromsampid={} and llsim<{} and samples.fid=similarity.withsampid and samples.src_layer='{}'\
         and samples.labelid={} order by llsim desc".format(sampleid,sim_threshhold,layername,labelid)
        print_log(sql)
        lblcur.execute(sql)
        odd_samples = lblcur.fetchall()
        if not odd_samples:
            self.update_sim_with_sameLabeled(sampleid,overwrite=True,close_connect=False)
            lblcur.execute(sql)
            odd_samples = lblcur.fetchall()
        lblcur.close()
        if close_connect:
            self.close()
        return odd_samples

    def getSimSamplesOfOtherLabel(self,layername,sampleid,labelid,sim_threshhold,close_connect=True):
        '''
        获取与指定sample相似(相似性高于sim_threshhold)但属于不同label的其他从layername中获取的samples
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        #sql="select withsampid,llsim, from similarity where fromsampid={}".format(sampleid)
        sql="select withsampid as sampid,labelid,llsim,longitude,latitude from similarity,samples\
         where fromsampid={} and llsim>={} and samples.fid=similarity.withsampid and samples.src_layer='{}'\
         and samples.labelid<>{} order by llsim desc".format(sampleid,sim_threshhold,layername,labelid)
        print_log(sql)
        lblcur.execute(sql)
        odd_samples = lblcur.fetchall()
        lblcur.close()
        if close_connect:
            self.close()
        return odd_samples


    def getLabelSamplesByLabelTitle(self,title,limit=5,orderby=None,close_connect=True):
        labelItem=self.getLabelItemByTitle(title,close_connect)
        if labelItem:
            return self.getLabelSamplesByLabelId(labelItem.id,limit,orderby,close_connect)
        else:
            return None

    def delLabelSamplesOfFeature(self,layername,featid,close_connect=True):
        '''
        删除图层中指定feature对应的sample
        '''
        if not self.connect(): return None
        try:
            lblcur = self.connection.cursor()
            sql="delete  from samples where src_layer='{}' and src_featid={}".format(layername,featid)
            #print_log(sql)
            lblcur.execute(sql)
            self.connection.commit()
            lblcur.close()
        except sqlite3.Error as error:
            print_log("Failed to delete item: ", error)
        finally:
            if close_connect:
                self.close()


    def insertLabelItem(self,labelItem,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            lblcur.execute("insert into labels(title,superid,cc,description,reshape_rule) values(?,?,?,?,?)",
                           (labelItem.title,labelItem.superid,labelItem.cc,labelItem.desc,','.join(labelItem.reshape_rule)))
            self.connection.commit()
            id=lblcur.lastrowid
            lblcur.close()
            #print_log("The id of the inserted row :", id)
            return id
        except sqlite3.Error as error:
            print_log("Failed to insert item into table", error)
            return -1
        finally:
            if close_connect:
                self.close()
            self.getLabelItems(close_connect)

    def updateLabelItem(self,labelItem,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            sql="update labels set title='{}',superid={},cc='{}',description='{}',reshape_rule='{}' where fid={}".format(
                            labelItem.title,labelItem.superid,labelItem.cc,labelItem.desc,",".join(labelItem.reshape_rule),labelItem.id)
            #print_log(sql)
            lblcur.execute("update labels set title='{}',superid={},cc='{}',description='{}',reshape_rule='{}' where fid={}".format(
                            labelItem.title,labelItem.superid,labelItem.cc,labelItem.desc,",".join(labelItem.reshape_rule),labelItem.id))
            self.connection.commit()
            lblcur.close()
            #print_log("Total number of rows updated :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to update item into table", error)
        finally:
            if close_connect:
                self.close()
            self.getLabelItems(close_connect)

    def delteLabelItem(self,labelid,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            lblcur.execute("delete from  labels where fid={}".format(labelid))
            self.connection.commit()
            lblcur.close()
            #print_log("Total number of rows deleted :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to delete item: ", error)
        finally:
            if close_connect:
                self.close()
            self.getLabelItems(close_connect)

    def getMostUsedLabelItems(self,min_used=1,close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select title,fid,superid,cc,description,reshape_rule from labels where used_times>={} order by used_times DESC".format(min_used))
        labels = lblcur.fetchall()
        lblcur.close()
        mostUsedItems=[]
        for label in labels:
            rules=label[5].split(",") if label[5] else []
            mostUsedItems.append(LabelItem(label[0], label[1], label[2], label[3],label[4], rules))
        if close_connect:
            self.close()
        return mostUsedItems

    def getLabelItemsByIds(self,ids=[],close_connect=True):
        if not self.connect(): return
        self.labelItems.clear()
        if len(ids)>0:
            lblcur = self.connection.cursor()
            lblcur.execute("select title,fid,superid,cc,description,reshape_rule from labels where fid in ({})".format(",".join(ids)))
            labels = lblcur.fetchall()
            lblcur.close()
            for label in labels:
                rules=label[5].split(",") if label[5] else []
                self.labelItems.append(LabelItem(label[0], label[1], label[2], label[3],label[4], rules))
        if close_connect:
            self.close()

    def toBlob(self,labelSample):
        '''
        将numpy数组转换为sqlite的blob
        '''
        import copy
        blobLS=copy.deepcopy(labelSample)
        if hasattr(labelSample,"gebd") and labelSample.gebd is not None:
            blobLS.gebd=sqlite3.Binary(labelSample.gebd.tobytes())
        if hasattr(labelSample,"lebd1") and labelSample.lebd1 is not None:
            blobLS.lebd1=sqlite3.Binary(labelSample.lebd1.tobytes())
        if hasattr(labelSample,"lebd2") and labelSample.lebd2 is not None:
            blobLS.lebd2=sqlite3.Binary(labelSample.lebd2.tobytes())
        if hasattr(labelSample,"samp_img") and labelSample.samp_img is not None:
            blobLS.samp_img=sqlite3.Binary(cv2.imencode(".jpg", labelSample.samp_img)[1].tobytes())
        if hasattr(labelSample,"ghis") and labelSample.ghis is not None:
            #print_log("Before insert Ghis：",labelSample.ghis.shape,labelSample.ghis.dtype)
            blobLS.ghis=sqlite3.Binary(labelSample.ghis.tobytes())
        if hasattr(labelSample,"lhis") and labelSample.lhis is not None:
            #print_log("Before insert Lhis：",labelSample.lhis.shape,labelSample.lhis.dtype)
            blobLS.lhis=sqlite3.Binary(labelSample.lhis.tobytes())
        return blobLS

    def insertLabelSample(self,labelSample,close_connect=True):
        tosave=self.toBlob(labelSample)
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            attrs=[attr for attr in dir(tosave) if "__" not in attr and "set_" not in attr]
            sql="insert into samples ( "
            vstr="values("
            i=0
            values=[]
            for attr in attrs:
                if attr=='fid':
                    continue
                v=getattr(tosave,attr)
                if v is not None:
                    if i>0:
                        sql +=","
                        vstr+=","
                    sql+= attr
                    vstr+="?"
                    values.append(v)
                i=i+1
            vstr+=")"
            sql = sql+ ")" +vstr

            values=tuple(values)
            lblcur.execute(sql,values)
            self.connection.commit()
            id = lblcur.lastrowid
            #print_log("insert a sample into db for label: ", labelSample.labelid)
            return id
        except sqlite3.Error as error:
            print_log("Failed to insert item into table,", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def updatelabelSampleFeatid(self,sampid,featid,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            lblcur.execute("update samples set src_featid={} where fid={}".format(featid,sampid))
            self.connection.commit()
            #print_log("Total number of rows updated :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to update src_featid", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def updateLabelSampleLabelid(self,featid,labelid,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            lblcur.execute("update samples set labelid={} where src_featid={}".format(labelid,featid))
            self.connection.commit()
            #print_log("Total number of rows updated :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to update labelid", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def updateLabelSample(self,labelSample,fields2update,close_connect=True):
        assert labelSample.fid>0, "Please specify the fid of the sample you want update"
        tosave=self.toBlob(labelSample)
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            attrs=[attr for attr in dir(tosave) if "__" not in attr and "set_" not in attr]
            sql="update samples set "
            i=0
            values=[]
            for attr in attrs:
                if attr=='fid':
                    continue
                v=getattr(tosave,attr)
                if attr in fields2update and v is not None:
                    if i>0:
                        sql +=","
                    sql+= "{} = ? ".format(attr)
                    values.append(v)
                i=i+1
            sql += " where fid=? "
            values.append(labelSample.fid)
            values=tuple(values)
            lblcur.execute(sql,values)
            self.connection.commit()
            #print_log("Total number of rows updated :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to update item into table", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def delteLabelSample(self,sampleid,close_connect=True):
        if not self.connect(): return
        try:
            lblcur = self.connection.cursor()
            lblcur.execute("delete from  samples where fid={})".format(sampleid))
            self.connection.commit()
            #print_log("Total number of rows deleted :", self.connection.total_changes)
        except sqlite3.Error as error:
            print_log("Failed to delete item", error)
        finally:
            lblcur.close()
            if close_connect:
                self.close()

    def refresh_pca_agents_of_alllabels(self,progress_bar,min_usedtimes=5,close_connect=True):
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select labelid from (select labelid,count(*) as nums from samples group by labelid) where nums>{}".format(min_usedtimes))
        labels = lblcur.fetchall()
        lblcur.close()
        if progress_bar is not None:
            self.set_progress_range(progress_bar,[0,len(labels)])
        i=0
        for labelid in labels:
            self.refresh_pca_of_label(labelid[0],close_connect=False)
            self.refresh_agents_of_label(labelid[0],close_connect=False)
            self.update_progress(progress_bar, i)
            QApplication.processEvents()
            i=i+1
        if close_connect:
            self.close()

    def refresh_pca_of_label(self,labelid,close_connect=True):
        '''
        提取labelid的embeding，如果超过5个，就计算所有该labell所有embedding的主成分，保存到ebdpca表中
        供判断相似性时使用
        PCAEngine:用于计算PCA的对象
        '''
        def PCA(data,n_components=1):
            '''
            data为一个R行C列的二维nparray,表示R个C维向量
            目的是生成较少数量(1个或最多3个)C维向量，用其其代表R个向量，这里的主要目标不是降低向量维度，而是生成能够代表R个样本的少数样本
            return: 如果n_components为大于等1的整数，就返回指定个数的主成分，如果为0-1的小数，就返回累计得分超过该值的所有主成分，否则返回所有
            '''
            data=np.squeeze(data)
            samp_mean=np.mean(data, axis=0) #各样本的C维平均值向量
            A = data.T #转置，将R视为要降低的维数
            MEAN = np.mean(A, axis=0)  # 沿轴0调用mean函数
            # 去中心化
            X = np.subtract(A, MEAN)
            # 计算协方差矩阵
            COV = np.dot(X.T, X)
            # 计算特征值和特征向量
            W, V = np.linalg.eig(COV)
            # 计算主成分贡献率以及累计贡献率
            sum_lambda = np.sum(W)  # 特征值的和
            ratios = np.divide(W, sum_lambda)  # 每个特征值的贡献率（特征值 / 总和）
            components=[]
            for i in range(len(ratios)):#降维后的结果（恢复均值水平）
                components.append(np.dot(A,V.T[i]))

            if n_components>=1 and type(n_components)==int:
                return components[:n_components],ratios[:n_components]

            elif n_components>0 and n_components<1:
                index=0
                sum_ratio=0
                for ratio in ratios:
                    index+=1
                    sum_ratio+=ratio
                    if sum_ratio>=n_components:
                        break
                return components[:index],ratios[:index]
            else:
                return components,ratios

        labelSamples=self.getLabelSamplesByLabelId(labelid,limit=-1,close_connect=close_connect)
        gebds=[]
        lebds=[]
        for samp in labelSamples:
            gebds.append(samp.gebd)
            lebds.append(samp.lebd1)
        gebds=np.array(gebds)
        lebds=np.array(lebds)
        g_pca,g_score = PCA(gebds, 1)
        l_pca,l_score = PCA(lebds, 1)
        #print_log("Label {}: The scores for the PCA of {} gembeddings:{}".format(labelid,len(labelSamples),g_score[0]))
        #print_log("Label {}: The scores for the PCA of lembedding:{}".format(labelid,l_score[0]))
        self.updateOrInsertLabelPCA(labelid,np.array(g_pca[0]),np.array(l_pca[0]),int(g_score[0]*100),int(l_score[0]*100),close_connect=close_connect)

    def get_cluster_cores(self,vectors):
        '''
        对样本进行聚类，并提取各个聚簇中的核心样本作为该类的代表。
        OPTICS聚类方法的结果可能可以通过判断每个聚簇中的reachability最小的样本作为代表样本，但比较麻烦，是否正确有待测试
        DBSCAN聚类方法返回core_sample_indices_，包含聚簇中包含的所有样本的索引，只能从中选取，但选取标准无法确定，因此选取结果的典型性无从判定
        HDBSACN通过指定store_centers="medoid"参数，可以在medoids_属性中返回代表每一个聚簇的一个典型样本，该样本为聚簇中与其他样本之间距离最小的样本，其典型性较好
        因此此处采用HDBSACN算法
        '''
        from sklearn.cluster import HDBSCAN
        X = np.squeeze(vectors)
        #必须指定allow_single_cluster=True，否则如果聚类结果只有一个聚簇，结果就会返回没有聚簇。
        min_cluster_size=5 if X.shape[0]>=5 else X.shape[0]
        hdb = HDBSCAN(min_cluster_size=min_cluster_size,n_jobs=-1,store_centers="medoid",allow_single_cluster=True).fit(X)
        #返回向量的个数为聚类后的聚簇数
        return hdb.medoids_


    def refresh_agents_of_label(self,labelid,close_connect=True):
        '''
        todo:to be finished,采用聚类簇的中心比基于centroid距离排序法更好。
         提取labelid的embeding，如果超过5个，就通过聚类计算该labell所有embedding的最具代表性的3个样本，保存到ebdpca表中的agents列中
         供判断相似性时使用
        '''
        def get_agents(data, n_components=3):
            '''
            data为一个R行C列的二维nparray,表示R个C维向量
            目的是找出其中法人3个C维向量，用其其代表全部R个向量
            return: 如果n_components为大于等1的整数，就返回指定个数的代表向量
            '''
            data = np.squeeze(data)
            samp_mean = np.mean(data, axis=0)  # 各样本的C维平均值向量
            distances=np.linalg.norm(data-samp_mean,axis=1)
            sorted_indeices=np.argsort(distances)
            result=data[sorted_indeices[:n_components]]
            return result

        labelSamples=self.getLabelSamplesByLabelId(labelid,limit=-1,close_connect=False)
        if len(labelSamples)>3: #如果样本不多于5个，没必要获取代表向量
            gebds=[]
            lebds=[]
            for samp in labelSamples:
                gebds.append(samp.gebd)
                lebds.append(samp.lebd1)
            gebds=np.array(gebds)
            lebds=np.array(lebds)
            g_agents = self.get_cluster_cores(gebds)
            l_agents = self.get_cluster_cores(lebds)
            self.updateOrInsertLabelAgents(labelid,np.array(g_agents),np.array(l_agents),close_connect=False)
            for  samp in labelSamples:
                self.update_sim_with_agents(g_agents,l_agents,samp.id,close_connect=close_connect)


    def getLabelPCA(self,labelid,close_connect=True):
        '''
        返回存储在数据库中的label的主成分矢量
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        sql="select gpca,lpca from ebdpca where labelid={}".format(labelid)
        #print_log(sql)
        lblcur.execute(sql)
        pcas = lblcur.fetchone()
        lblcur.close()
        if pcas:
            gpca=np.frombuffer(pcas[0],dtype=np.float32).reshape((1, -1))
            lpca=np.frombuffer(pcas[1],dtype=np.float32).reshape((1, -1))
        else:
            gpca = None
            lpca = None
        if close_connect:
            self.close()
        return gpca,lpca

    def updateOrInsertLabelPCA(self,labelid,gpca,lpca,g_score,l_score,close_connect=True):
        '''
        存储主成分矢量
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select count(*) from  ebdpca where labelid={}".format(labelid))
        result = lblcur.fetchone()
        if result[0]>0:
            sql="update ebdpca set gpca=?,lpca=?,gscore=?,lscore=? where labelid={}".format(labelid)
            lblcur.execute(sql, (sqlite3.Binary(gpca.tobytes()), sqlite3.Binary(lpca.tobytes()),g_score,l_score))
        else:
            sql="insert into ebdpca(labelid,gpca,lpca,gscore,lscore) values(?,?,?,?,?)"
            lblcur.execute(sql, (labelid,sqlite3.Binary(gpca.tobytes()), sqlite3.Binary(lpca.tobytes()),g_score,l_score))

        self.connection.commit()
        id = lblcur.lastrowid
        #print_log("updateOrInsertLabelPCA, Inserted id:",id)
        lblcur.close()
        if close_connect:
            self.close()

    def updateOrInsertLabelAgents(self,labelid,g_agents,l_agents,close_connect=True):
        '''
        保存label的若干代表性样本（1-N，N为通过HDBSCAN算法聚类结果的聚簇数）
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        #print_log("In LabelBase.updateOrInsertLabelAgents:",labelid,g_agents.shape,l_agents.shape)

        lblcur.execute("select count(*) from  ebdpca where labelid={}".format(labelid))
        result = lblcur.fetchone()
        if result[0]>0:
            sql="update ebdpca set gagents=?,lagents=?, gagent_count=?,lagent_count=?  where labelid={}".format(labelid)
            lblcur.execute(sql, (sqlite3.Binary(g_agents.tobytes()), sqlite3.Binary(l_agents.tobytes()),g_agents.shape[0],l_agents.shape[0]))
        else:
            sql="insert into ebdpca(labelid,gagents,lagents,gagent_count,lagent_count) values(?,?,?,?,?)"
            lblcur.execute(sql, (labelid,sqlite3.Binary(g_agents.tobytes()), sqlite3.Binary(l_agents.tobytes()),g_agents.shape[0],l_agents.shape[0]))

        self.connection.commit()
        id = lblcur.lastrowid
        print_log("updateOrInsertLabelAgents, Inserted id:",id)
        lblcur.close()
        if close_connect:
            self.close()

    def update_sim_with_pca(self,labelid,sampleid,close_connect=True):
        '''
        更新sampleid对应的sample与其label主成分PCA的相似度
        '''
        def cos_sim(vector_a, vector_b):
          """
          计算两个向量之间的余弦相似度
          :param vector_a: 向量 a
          :param vector_b: 向量 b
          :return: sim
          """
          vector_a = np.mat(vector_a)
          vector_b = np.mat(vector_b)
          num = float(vector_a * vector_b.T)
          denom = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
          sim = num / denom
          return sim

        label_sample = self.getLabelSampleById(sampleid,close_connect=close_connect)
        gpca,lpcal=self.getLabelPCA(labelid,close_connect=close_connect)

        gsim_pca=cos_sim(gpca,label_sample.gebd) if gpca else 0
        lsim_pca=cos_sim(lpcal,label_sample.lebd1) if lpca else 0

        if gsim_pca>0 or lsim_pca>0:
            if not self.connect(): return
            try:
                lblcur = self.connection.cursor()
                lblcur.execute("update samples set gsim_pca=?, lsim_pca=?  where sampleid=?",
                               (gsim_pca,lsim_pca,sampleid))
                self.connection.commit()
                #print_log("Total number of rows updated :", self.connection.total_changes)
            except sqlite3.Error as error:
                print_log("Failed to update item into table", error)
            finally:
                lblcur.close()
                if close_connect:
                    self.close()

    def getLabelsAgentsPcaByIds(self,labelids,close_connect=True):
        '''
        返回存储在数据库中的label的代表性样本和主成分结果
        为{labelid=[gagents,lagents,gpca,lpca]}组成的Dict
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        ids_str=",".join([str(id) for id in labelids])
        sql="select labelid,gagents,lagents,gpca,lpca,gagent_count,lagent_count from ebdpca where gagents is not Null and lagents is not Null and labelid in ({})".format(ids_str)
        #print_log("In getLabelsAgentsPcaByIds:",sql)
        lblcur.execute(sql)
        results = lblcur.fetchall()
        lblcur.close()
        agents={}
        if results:
            for agent in results:
                #print_log("In labelBase.getLabelAgentsById:",agent[0],agent[5],agent[6])
                gagents=np.frombuffer(agent[1],dtype=np.float64).reshape((agent[5], -1))
                lagents=np.frombuffer(agent[2],dtype=np.float64).reshape((agent[6], -1))
                gpca = np.frombuffer(agent[3], dtype=np.float32).reshape((1, -1))
                lpca = np.frombuffer(agent[4], dtype=np.float32).reshape((1, -1))
                #print_log("In labelBase.getLabelAgentsById:",gagents.shape,lagents.shape)
                #print_log("In getLabelsAgentsPcaByIds:",agent[0],type(agent[0]))
                agents[agent[0]]=[gagents,lagents,gpca,lpca]
        if close_connect:
            self.close()
        return agents

    def getLabelAgentsById(self, labelid, close_connect=True):
        '''
        返回存储在数据库中的label的主成分矢量
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        sql="select gagents,lagents,gagent_count,lagent_count from ebdpca where gagents is not Null and lagents is not Null and labelid={}".format(labelid)
        #print_log(sql)
        lblcur.execute(sql)
        agents = lblcur.fetchone()
        lblcur.close()
        if agents:
            #print_log("In labelBase.getLabelAgentsById:",labelid,agents[2],agents[3])
            gagents=np.frombuffer(agents[0],dtype=np.float64).reshape((agents[2], -1))
            lagents=np.frombuffer(agents[1],dtype=np.float64).reshape((agents[3], -1))
            #print_log("In labelBase.getLabelAgentsById:",gagents.shape,lagents.shape)
            #print_log(gagents)
        else:
            gagents = None
            lagents = None
        if close_connect:
            self.close()
        return gagents,lagents

    def update_sim_with_agents(self,gagents,lagents,sampleid,close_connect=True):
        '''
        更新sampleid对应的sample与其label各个代表性样本的相似度的最大值
        '''
        def cos_sim(vector_a, vector_b):
          """
          计算两个向量之间的余弦相似度
          :param vector_a: 向量 a
          :param vector_b: 向量 b
          :return: sim
          """
          vector_a = np.mat(vector_a)
          vector_b = np.mat(vector_b)
          num = float(vector_a * vector_b.T)
          denom = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
          sim = num / denom
          return sim

        label_sample = self.getLabelSampleById(sampleid,close_connect=close_connect)
        max_gsim = 0
        max_lsim = 0
        if gagents is not None and lagents is not None:
            for gagent in gagents:
                gsim=cos_sim(gagent,label_sample.gebd) if gagents is not None else 0
                if gsim>max_gsim:
                    max_gsim=gsim
            for lagent in lagents:
                lsim=cos_sim(lagent,label_sample.lebd1) if lagents is not None else 0
                if lsim>max_lsim:
                    max_lsim=lsim

        if max_gsim>0 or max_lsim>0:
            if not self.connect(): return
            try:
                lblcur = self.connection.cursor()
                lblcur.execute("update samples set gsim_agents=?, lsim_agents=?  where fid=?",
                               (max_gsim,max_lsim,sampleid))
                self.connection.commit()
                #print_log("Total number of rows updated :", self.connection.total_changes)
            except sqlite3.Error as error:
                print_log("Failed to update item into table", error)
            finally:
                lblcur.close()
                if close_connect:
                    self.close()

    def update_or_insert_siminfo_between(self,fromsampid,withsampid,overwrite=True,close_connect=True,skipExisting=False):
        '''
        更新或插入两个sample之间的相似性计算结果
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute(
            "select count(*) from  similarity where fromsampid={} and withsampid={}".format(fromsampid, withsampid))
        result = lblcur.fetchone()
        if result[0] > 0 and skipExisting:
            pass
        else:
            fromsamp=self.getLabelSampleById(fromsampid,close_connect=False)
            withsamp=self.getLabelSampleById(withsampid,close_connect=False)
            ggsim=cosine_similarity(fromsamp.gebd, withsamp.gebd)
            glsim=cosine_similarity(fromsamp.gebd, withsamp.lebd1)
            llsim=cosine_similarity(fromsamp.lebd1, withsamp.lebd1)
            lgsim=cosine_similarity(fromsamp.lebd1, withsamp.gebd)
            ggcorrcoef=correlation_coefficient(fromsamp.gebd, withsamp.gebd)
            glcorrcoef=correlation_coefficient(fromsamp.gebd, withsamp.lebd1)
            llcorrcoef=correlation_coefficient(fromsamp.lebd1, withsamp.lebd1)
            lgcorrcoef=correlation_coefficient(fromsamp.lebd1, withsamp.gebd)
            mutualinfo=mutual_info(fromsamp.samp_img, withsamp.samp_img)
            gghissim=cosine_similarity(fromsamp.ghis, withsamp.ghis)
            glhissim=cosine_similarity(fromsamp.ghis, withsamp.lhis)
            llhissim=cosine_similarity(fromsamp.lhis, withsamp.lhis)
            lghissim=cosine_similarity(fromsamp.lhis, withsamp.ghis)

            maxsim=max([ggsim,glsim,llsim,lgsim,ggcorrcoef,glcorrcoef,llcorrcoef,lgcorrcoef,gghissim,glhissim,llhissim,lghissim])
            #if all similarities are all less than 50 for the different label, then do not store in database to save space
            if (fromsamp.labelid!=withsamp.labelid and maxsim>50) or fromsamp.labelid==withsamp.labelid:
                if result[0]>0 and overwrite:
                    sql="update similarity set ggsim=?,glsim=?, llsim=?,lgsim=?,ggcorrcoef=?,glcorrcoef=?,llcorrcoef=?,lgcorrcoef=?," \
                        "mutualinfo=?,gghissim=?,glhissim=?,llhissim=?,lghissim=? where fromsampid={} and withsampid={}".format(fromsampid,withsampid)
                    lblcur.execute(sql, (ggsim,glsim,llsim,lgsim,ggcorrcoef,glcorrcoef,llcorrcoef,lgcorrcoef,
                                         mutualinfo,gghissim,glhissim,llhissim,lghissim
                                         )
                                   )
                else:
                    sql="insert into similarity(fromsampid,withsampid,ggsim,glsim,llsim,lgsim,ggcorrcoef,glcorrcoef,llcorrcoef,lgcorrcoef," \
                        "mutualinfo,gghissim,glhissim,llhissim,lghissim) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    #print_log("********************************************\n", fromsamp.ghis.shape,withsamp.ghis.shape,fromsamp.ghis, withsamp.ghis)
                    #print_log("********************************************\n", fromsamp.lhis.shape,withsamp.lhis.shape,fromsamp.lhis, withsamp.lhis)
                    lblcur.execute(sql, (fromsampid,withsampid,
                                         ggsim, glsim, llsim, lgsim, ggcorrcoef, glcorrcoef, llcorrcoef, lgcorrcoef,
                                         mutualinfo, gghissim, glhissim, llhissim, lghissim
                                         )
                                   )
                self.connection.commit()
                id = lblcur.lastrowid
                #print_log("Inserted id:",id)
                lblcur.close()
        if close_connect:
            self.close()

    def update_sim_with_eachother(self,overwrite=True,progress_bar=None,close_connect=True,skipExisting=False):
        '''
        更新sample两两之间的相似性计算结果
        overwrite:如果已经存在，是否覆盖更新
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select fid,labelid from samples order by fid DESC")
        result = lblcur.fetchall()
        lblcur.close()

        if progress_bar is not None:
            self.set_progress_range(progress_bar,[0,len(result)**2/2])
        i=0
        for fromid in result:
            for withid in result:
                i = i + 1
                if progress_bar is not None:
                    self.update_progress(progress_bar, i)
                    QApplication.processEvents()
                if fromid[0]<=withid[0]:
                    continue
                self.update_or_insert_siminfo_between(fromid[0],withid[0],overwrite=overwrite,close_connect=False,skipExisting=skipExisting)
                if self.interruptLongTransaction:
                    break
            if self.interruptLongTransaction:
                self.update_progress(progress_bar, len(result)**2/2)
                break
        if close_connect:
            self.close()
        self.setInterruptLongTransaction(False)

    def update_sim_with_sameLabeled(self,this_sampleid,overwrite=True,progress_bar=None,close_connect=True):
        '''
        更新指定sample与同一类其他sample两两之间的相似性计算结果
        overwrite:如果已经存在，是否覆盖更新
        '''
        if not self.connect(): return
        lblcur = self.connection.cursor()
        lblcur.execute("select labelid from samples where fid={}".format(this_sampleid))
        labelid = lblcur.fetchone()
        if labelid:
            lblcur.execute("select fid from samples where fid<>{} and labelid={}".format(this_sampleid,labelid[0]))
            result = lblcur.fetchall()
            lblcur.close()
            if progress_bar is not None:
                self.set_progress_range(progress_bar,[0,len(result)**2])
            i=0
            for withid in result:
                i = i + 1
                if progress_bar is not None:
                    self.update_progress(progress_bar, i)
                self.update_or_insert_siminfo_between(this_sampleid,withid[0],overwrite=overwrite,close_connect=False)
        if close_connect:
            self.close()

    def update_progress(self,progress_bar,value):
        progress_bar.setValue(value)

    def set_progress_range(self,progress_bar,range):
        progress_bar.setRange(range[0],range[1])

    def setInterruptLongTransaction(self,state=True):
        self.interruptLongTransaction=state
