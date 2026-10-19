from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    details = response.data
    if isinstance(details, dict) and "detail" in details:
        message = str(details["detail"])
        fields = None
    else:
        message = "Dados inválidos."
        fields = details
    response.data = {"error": {"code": getattr(exc, "default_code", "error"), "message": message}}
    if fields is not None:
        response.data["error"]["fields"] = fields
    return response
