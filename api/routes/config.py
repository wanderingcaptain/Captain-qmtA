import os
import tomli
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from config import Config

router = APIRouter()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "settings.toml")

class ConfigUpdateModel(BaseModel):
    section: str
    key: str
    value: Any

@router.get("/")
def get_config():
    """获取整个 settings.toml 的原始结构"""
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail="settings.toml not found")
        
    with open(CONFIG_PATH, "rb") as f:
        data = tomli.load(f)
    return {"status": "success", "data": data}

@router.post("/")
def update_config(update: ConfigUpdateModel):
    """
    修改 settings.toml 的单个配置。
    注意：为了简单处理写回，我们需要重写整个文件。在生产环境中应谨慎处理。
    """
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail="settings.toml not found")
        
    with open(CONFIG_PATH, "rb") as f:
        data = tomli.load(f)
        
    if update.section not in data:
        data[update.section] = {}
        
    data[update.section][update.key] = update.value
    
    # 简单的 TOML 写入（因为 Python 标准库没有写 TOML 的，可以用简单的字符串拼接，这里为了稳定引入手写 formatter）
    _write_toml(data, CONFIG_PATH)
    
    # 重载全局配置
    Config._load_toml()
    
    return {"status": "success", "message": f"Updated [{update.section}] {update.key}"}

def _write_toml(data: dict, filepath: str):
    """简易的 TOML 写入器（仅支持平铺字典格式）"""
    lines = []
    for section, keys in data.items():
        lines.append(f"[{section}]")
        for k, v in keys.items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, bool):
                lines.append(f'{k} = {"true" if v else "false"}')
            elif isinstance(v, (int, float)):
                lines.append(f'{k} = {v}')
            else:
                # 列表或复杂结构，退化为字符串表达
                lines.append(f'{k} = {str(v)}')
        lines.append("")
        
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
