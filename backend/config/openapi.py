"""Schema for plain Django session views not discoverable by DRF introspection."""

ERROR = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["code", "message"],
        }
    },
    "required": ["error"],
}
USER = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "username": {"type": "string"},
                "name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "is_staff": {"type": "boolean"},
                "must_change_password": {"type": "boolean"},
            },
            "required": ["id", "username", "is_staff", "must_change_password"],
        }
    },
    "required": ["user"],
}

AUTH_PATHS = {
    "/api/v1/csrf/": {
        "get": {
            "tags": ["Sessão"],
            "operationId": "get_csrf_cookie",
            "description": "Obtém cookie CSRF antes de login e requisições mutáveis.",
            "responses": {"200": {"description": "Cookie CSRF enviado"}},
        }
    },
    "/api/v1/login/": {
        "post": {
            "tags": ["Sessão"],
            "operationId": "login",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "password": {"type": "string", "format": "password"},
                            },
                            "required": ["username", "password"],
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Sessão criada",
                    "content": {"application/json": {"schema": USER}},
                },
                "400": {
                    "description": "Dados inválidos",
                    "content": {"application/json": {"schema": ERROR}},
                },
                "401": {
                    "description": "Credenciais inválidas",
                    "content": {"application/json": {"schema": ERROR}},
                },
            },
        }
    },
    "/api/v1/logout/": {
        "post": {
            "tags": ["Sessão"],
            "operationId": "logout",
            "security": [{"cookieAuth": []}],
            "responses": {
                "200": {"description": "Sessão encerrada"},
                "401": {
                    "description": "Não autenticado",
                    "content": {"application/json": {"schema": ERROR}},
                },
            },
        }
    },
    "/api/v1/session/": {
        "get": {
            "tags": ["Sessão"],
            "operationId": "get_session",
            "security": [{"cookieAuth": []}],
            "responses": {
                "200": {
                    "description": "Usuário atual",
                    "content": {"application/json": {"schema": USER}},
                },
                "401": {
                    "description": "Não autenticado",
                    "content": {"application/json": {"schema": ERROR}},
                },
            },
        }
    },
    "/api/v1/sector-members/": {
        "get": {
            "tags": ["Conta"],
            "operationId": "list_sector_members",
            "description": "Lista membros ativos do mesmo setor para transferência de reunião.",
            "security": [{"cookieAuth": []}],
            "responses": {
                "200": {
                    "description": "Membros ativos do setor",
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "members": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "username": {"type": "string"},
                                        "name": {"type": "string"},
                                    },
                                    "required": ["id", "username", "name"],
                                },
                            }
                        },
                        "required": ["members"],
                    }}},
                },
                "401": {
                    "description": "Não autenticado",
                    "content": {"application/json": {"schema": ERROR}},
                },
            },
        }
    },
    "/api/v1/account/": {
        "get": {
            "tags": ["Conta"],
            "operationId": "get_account",
            "security": [{"cookieAuth": []}],
            "responses": {
                "200": {
                    "description": "Dados da conta",
                    "content": {"application/json": {"schema": USER}},
                }
            },
        },
        "patch": {
            "tags": ["Conta"],
            "operationId": "update_account",
            "security": [{"cookieAuth": []}],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string", "format": "email"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Conta atualizada",
                    "content": {"application/json": {"schema": USER}},
                }
            },
        },
    },
    "/api/v1/account/password/": {
        "post": {
            "tags": ["Conta"],
            "operationId": "change_password",
            "security": [{"cookieAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "currentPassword": {"type": "string", "format": "password"},
                                "newPassword": {"type": "string", "format": "password"},
                            },
                            "required": ["currentPassword", "newPassword"],
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Senha atualizada; libera o primeiro acesso quando obrigatório"
                },
                "400": {
                    "description": "Senha atual incorreta ou nova senha inválida",
                    "content": {"application/json": {"schema": ERROR}},
                },
            },
        }
    },
}
