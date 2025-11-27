from fastapi.responses import JSONResponse

def format_response(status_code: int, status: str, data: dict):
    return JSONResponse(
        status_code=status_code,
        content={
            "statusCode": status_code,
            "status": status,
            "data": data
        }
    )