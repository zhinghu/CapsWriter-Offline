import asyncio

from util.client_cosmic import Cosmic, console
from config import ClientConfig as Config
import numpy as np
import base64
import json
import websockets
from util.client_create_file import create_file
from util.client_write_file import write_file
from util.client_finish_file import finish_file
import uuid



async def send_message(message):
    # 发送数据
    if Cosmic.websocket is None or Cosmic.websocket.closed:
        if message['is_final']:
            Cosmic.audio_files.pop(message['task_id'])
            console.print('    服务端未连接，无法发送\n')
    else:
        try:
            await Cosmic.websocket.send(json.dumps(message))
        except websockets.ConnectionClosedError as e:
            if message['is_final']:
                console.print(f'[red]连接中断了')
        except Exception as e:
            print('出错了')
            print(e)


async def send_audio():
    try:

        # 生成唯一任务 ID
        task_id = str(uuid.uuid1())

        # 任务起始时间
        time_start = 0

        # 音频数据临时存放处
        cache = []
        duration = 0

        # 保存音频文件
        file_path, file = '', None

        # 开始取数据
        # task: {'type', 'time', 'data'}
        while task := await Cosmic.queue_in.get():
            Cosmic.queue_in.task_done()
            match task['type']:
                case 'begin':
                    time_start = task['time']
                case 'data':
                    # 在阈值之前积攒音频数据
                    if task['time'] - time_start < Config.threshold:
                        cache.append(task['data'])
                        continue

                    # 创建音频文件
                    if not file_path:
                        file_path, file = create_file(task['data'].shape[1], time_start)
                        Cosmic.audio_files[task_id] = file_path

                    # 获取音频数据
                    if cache:
                        data = np.concatenate(cache)
                        cache.clear()
                    else:
                        data = task['data']

                    # 保存音频至本地文件
                    duration += len(data) / 48000
                    write_file(file, data)

                    # 发送音频数据用于识别
                    message = {
                        'task_id': task_id,
                        'is_final': False,
                        'time_start': time_start,
                        'time_frame': task['time'],
                        'data': base64.b64encode(
                                    np.mean(data[::3], axis=1).tobytes()
                                ).decode('utf-8'),
                    }
                    task = asyncio.create_task(send_message(message))
                case 'finish':
                    # 完成写入本地文件
                    finish_file(file)

                    console.print(f'任务标识：{task_id}')
                    console.print(f'    录音时长：{duration:.2f}s')

                    # 告诉服务端音频片段结束了
                    message = {
                        'task_id': task_id,
                        'is_final': True,
                        'time_start': time_start,
                        'time_frame': task['time'],
                        'data': '',
                    }
                    task = asyncio.create_task(send_message(message))
                    break
    except Exception as e:
        print(e)