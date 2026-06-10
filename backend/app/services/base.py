from fastapi import HTTPException, status


class BaseService:
    def not_implemented(self, detail: str = "Service method not implemented yet") -> None:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail)
