"""Closed compatibility entrypoints for the retired active-submission queue.

Content workers independently scan planner rows with bank-authorized read access.
Python only reads production status through app.content_planning.services.content_status.
"""
from fastapi import HTTPException

def retired(*args, **kwargs):
    raise HTTPException(410, '主动投递队列已停用，请使用同库扫描与生产结果回写')

enqueue_batch = retired
batch_flow = retired
receive_result = retired
