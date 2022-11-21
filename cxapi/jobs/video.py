import json
import re
import time
import urllib.parse
from hashlib import md5

import requests
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress

from ..utils import get_dc

PAGE_MOBILE_CHAPTER_CARD = 'https://mooc1-api.chaoxing.com/knowledge/cards'      # SSR页面-客户端章节任务卡片
API_CHAPTER_CARD_RESOURCE = 'https://mooc1-api.chaoxing.com/ananas/status'       # 接口-课程章节卡片资源
API_VIDEO_PLAYREPORT = 'https://mooc1-api.chaoxing.com/multimedia/log/a'         # 接口-视频播放上报


class ChapterVideo:
    '章节视频'
    session: requests.Session
    # 基本参数
    clazzid: int
    courseid: int
    knowledgeid: int
    card_index: int  # 卡片索引位置
    point_index: int  # 任务点索引位置
    cpi: int
    puid: int
    # 视频参数
    objectid: str
    fid: int
    dtoken: str
    duration: int
    jobid: str
    otherInfo: str
    title: str
    
    def __init__(self, session: requests.Session, clazzid: int, courseid: int, knowledgeid: int, card_index: int, objectid: str, cpi: int, puid: int, point_index: int) -> None:
        self.session = session
        self.clazzid = clazzid
        self.courseid = courseid
        self.knowledgeid = knowledgeid
        self.card_index = card_index
        self.objectid = objectid
        self.cpi = cpi
        self.puid = puid
        self.point_index = point_index
    
    def pre_fetch(self) -> bool:
        '预拉取视频  返回是否需要完成'
        resp = self.session.get(PAGE_MOBILE_CHAPTER_CARD, params={
            'clazzid': self.clazzid,
            'courseid': self.courseid,
            'knowledgeid': self.knowledgeid,
            'num': self.card_index,
            'isPhone': 1,
            'control': 'true',
            'cpi': self.cpi
        })
        resp.raise_for_status()
        try:
            if r := re.search(r'window\.AttachmentSetting *= *(.+?);', resp.text):
                j = json.loads(r.group(1))
            else:
                raise ValueError
            self.fid = j['defaults']['fid']
            self.jobid = j['attachments'][self.point_index]['jobid']
            self.otherInfo = j['attachments'][self.point_index]['otherInfo']
            needtodo = j['attachments'][self.point_index].get('isPassed') in (False, None)
        except Exception:
            raise RuntimeError('视频预拉取出错')
        return needtodo
    
    def fetch(self) -> bool:
        '拉取视频'
        resp = self.session.get(
            f'{API_CHAPTER_CARD_RESOURCE}/{self.objectid}',
            params={
                'k': self.fid,
                'flag': 'normal',
                '_dc': get_dc()
            }
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.dtoken = json_content['dtoken']
        self.duration = json_content['duration']
        self.title = json_content['filename']
        return True
    
    def __play_report(self, playing_time: int) -> dict:
        '播放上报'
        def _mk_sign():
            '生成上报hash签名'
            return md5(f'[{self.clazzid}][{self.puid}][{self.jobid}][{self.objectid}][{playing_time * 1000}][d_yHJ!$pdA~5][{self.duration * 1000}][0_{self.duration}]'.encode()).hexdigest()
        
        resp = self.session.get(
            f'{API_VIDEO_PLAYREPORT}/{self.cpi}/{self.dtoken}',
            params=urllib.parse.urlencode({
                'otherInfo': self.otherInfo,
                'playingTime': playing_time,
                'duration': self.duration,
                # 'akid': None,
                'jobid': self.jobid,
                'clipTime': f'0_{self.duration}',
                'clazzId': self.clazzid,
                'objectId': self.objectid,
                'userid': self.puid,
                'isdrag': '0',
                'enc': _mk_sign(),
                'rt': '0.9',  # 'rt': '1.0',  ??
                'dtype': 'Video',
                'view': 'pc',
                '_t': int(time.time()*1000)
            }, safe='&=')  # 这里不需要编码`&`和`=`否则报403
        )
        resp.raise_for_status()
        json_content = resp.json()
        return json_content
    
    def playing(self, tui_ctx: Layout, speed: float=1.0, report_rate: int=58) -> None:
        '开始模拟播放视频'
        s_counter = report_rate
        playing_time = 0
        progress = Progress()
        info = Layout()
        tui_ctx.split_column(info, Panel(progress, title=f'模拟播放视频[green]《{self.title}》[/]', border_style='yellow'))
        bar = progress.add_task('playing...', total=self.duration)
        def _update_bar():
            '更新进度条'
            progress.update(
                bar,
                completed=playing_time,
                description=f"playing... [blue]{playing_time // 60:02d}:{playing_time % 60:02d}[/blue] [yellow]{report_rate - s_counter}s后汇报[/yellow](X{speed})"
            )
        while True:
            if s_counter >= report_rate:
                s_counter = 0
                report_result = self.__play_report(playing_time)
                j = JSON.from_data(report_result, ensure_ascii=False)
                if report_result.get('error'):
                    info.update(Panel(j, title='上报失败', border_style='red'))
                else:
                    info.update(Panel(j, title='上报成功', border_style='green'))
                if report_result.get('isPassed') == True:
                    playing_time = self.duration  # 强制100%, 解决强迫症
                    _update_bar()
                    info.update(Panel('OHHHHHHHH', title='播放完毕', border_style='green'))
                    time.sleep(5.0)
                    break
            playing_time += round(1 * speed)
            s_counter += round(1 * speed)
            _update_bar()
            time.sleep(1.0)

__all__ = ['ChapterVideo']