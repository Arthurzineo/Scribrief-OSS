from rest_framework.exceptions import ValidationError


def _positive_int(value, name):
    try:
        result = int(value)
        if result > 0:
            return result
    except (ValueError, TypeError):
        pass
    raise ValidationError({name: "Identificador inválido."})
