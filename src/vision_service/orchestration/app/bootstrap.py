from fastapi import FastAPI, UploadFile, File, HTTPException
import uvicorn
import os
import time
from typing import Any

import random

def generate_tube_coordinates():
    """
    Генерирует словарь tube_coordinates со случайными значениями для тестов.
    Все координаты - числа с плавающей точкой.
    """
    tube_coordinates = {
        "x": float(random.randint(-50, 50) + 300),      # float
        "y": float(random.randint(-50, 50)),            # float
        "z": float(random.randint(-50, 50) + 300),      # float
        "a": round(random.uniform(-20, 20), 1),         # уже float
        "b": round(random.uniform(-20, 20), 1),         # уже float
        "c": round(random.uniform(-20, 20), 1) + 90     # уже float
    }
    return tube_coordinates

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/predict")
async def predict(image: UploadFile = File(...)) -> dict[str, Any]:
    """
    ТЕСТОВЫЙ predict:
    - принимает файл изображения
    - "делает вид", что обработал
    - возвращает координаты tube_coordinates в формате, который ждёт robot
    """
    try:
        content = await image.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty image")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad image: {e}")

    # имитация времени инференса
    time.sleep(0.05)

    return generate_tube_coordinates()

def main():
    host = os.getenv("VISION_HOST", "127.0.0.1")
    port = int(os.getenv("VISION_PORT", "8010"))
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()