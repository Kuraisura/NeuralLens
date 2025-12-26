"""
Flask REST API with OpenAPI/Swagger Documentation
Auto-generated API documentation for Neural Lens

Features:
- OpenAPI 3.0 specification
- Swagger UI for interactive testing
- Auto-generated from Flask routes
- Request/response schemas
- Authentication documentation

Author: Neural Lens Development Team
Date: January 4, 2026
"""

from flask import Flask, jsonify, request
from flask_swagger_ui import get_swaggerui_blueprint
from functools import wraps
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging


# OpenAPI specification
OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "Neural Lens API",
        "description": "Face Recognition Attendance System REST API",
        "version": "1.0.0",
        "contact": {
            "name": "Neural Lens Development Team",
            "email": "support@neurallens.com"
        },
        "license": {
            "name": "Proprietary",
            "url": "https://neurallens.com/license"
        }
    },
    "servers": [
        {
            "url": "http://localhost:5000/api",
            "description": "Development server"
        },
        {
            "url": "https://api.neurallens.com",
            "description": "Production server"
        }
    ],
    "tags": [
        {"name": "Authentication", "description": "User authentication and authorization"},
        {"name": "Face Recognition", "description": "Face recognition and enrollment"},
        {"name": "Attendance", "description": "Attendance tracking and management"},
        {"name": "Users", "description": "User management"},
        {"name": "Leaves", "description": "Leave management"},
        {"name": "Reports", "description": "Report generation"},
        {"name": "System", "description": "System monitoring and health"},
        {"name": "Configuration", "description": "System configuration"}
    ],
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        },
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "example": 1},
                    "username": {"type": "string", "example": "john.doe"},
                    "email": {"type": "string", "format": "email", "example": "john@example.com"},
                    "full_name": {"type": "string", "example": "John Doe"},
                    "role": {"type": "string", "enum": ["admin", "user"], "example": "user"},
                    "department": {"type": "string", "example": "Engineering"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "AttendanceRecord": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "check_in": {"type": "string", "format": "date-time"},
                    "check_out": {"type": "string", "format": "date-time", "nullable": True},
                    "status": {"type": "string", "enum": ["present", "late", "absent"]},
                    "hours_worked": {"type": "number", "format": "float"}
                }
            },
            "LeaveRequest": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                    "reason": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "approved", "rejected"]},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            },
            "SystemHealth": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["healthy", "warning", "critical"]},
                    "cpu_percent": {"type": "number", "format": "float"},
                    "memory_percent": {"type": "number", "format": "float"},
                    "disk_usage": {"type": "number", "format": "float"},
                    "temperature": {"type": "number", "format": "float"},
                    "uptime": {"type": "integer"}
                }
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"},
                    "status": {"type": "integer"}
                }
            }
        }
    },
    "paths": {
        "/auth/login": {
            "post": {
                "tags": ["Authentication"],
                "summary": "User login",
                "description": "Authenticate user and receive JWT token",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["username", "password"],
                                "properties": {
                                    "username": {"type": "string", "example": "john.doe"},
                                    "password": {"type": "string", "format": "password", "example": "SecurePass123!"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "token": {"type": "string"},
                                        "user": {"$ref": "#/components/schemas/User"}
                                    }
                                }
                            }
                        }
                    },
                    "401": {
                        "description": "Invalid credentials",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        }
                    }
                }
            }
        },
        "/auth/logout": {
            "post": {
                "tags": ["Authentication"],
                "summary": "User logout",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {"description": "Logout successful"}
                }
            }
        },
        "/face/enroll": {
            "post": {
                "tags": ["Face Recognition"],
                "summary": "Enroll new face",
                "description": "Capture and store face encoding for user",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["user_id", "image"],
                                "properties": {
                                    "user_id": {"type": "integer"},
                                    "image": {"type": "string", "format": "binary"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Face enrolled successfully"},
                    "400": {"description": "Invalid image or no face detected"}
                }
            }
        },
        "/face/recognize": {
            "post": {
                "tags": ["Face Recognition"],
                "summary": "Recognize face",
                "description": "Identify person from image",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["image"],
                                "properties": {
                                    "image": {"type": "string", "format": "binary"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Face recognized",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "recognized": {"type": "boolean"},
                                        "user_id": {"type": "integer"},
                                        "name": {"type": "string"},
                                        "confidence": {"type": "number"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/attendance": {
            "get": {
                "tags": ["Attendance"],
                "summary": "Get attendance records",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "query",
                        "schema": {"type": "integer"},
                        "description": "Filter by user ID"
                    },
                    {
                        "name": "start_date",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                        "description": "Start date for filtering"
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                        "description": "End date for filtering"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Attendance records retrieved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/AttendanceRecord"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Attendance"],
                "summary": "Mark attendance",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["user_id", "type"],
                                "properties": {
                                    "user_id": {"type": "integer"},
                                    "type": {"type": "string", "enum": ["check_in", "check_out"]}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Attendance marked"}
                }
            }
        },
        "/users": {
            "get": {
                "tags": ["Users"],
                "summary": "Get all users",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Users retrieved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Users"],
                "summary": "Create new user",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/User"}
                        }
                    }
                },
                "responses": {
                    "201": {"description": "User created"}
                }
            }
        },
        "/users/{user_id}": {
            "get": {
                "tags": ["Users"],
                "summary": "Get user by ID",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "User retrieved",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    }
                }
            }
        },
        "/leaves": {
            "get": {
                "tags": ["Leaves"],
                "summary": "Get leave requests",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Leave requests retrieved",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/LeaveRequest"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Leaves"],
                "summary": "Submit leave request",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/LeaveRequest"}
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Leave request submitted"}
                }
            }
        },
        "/reports/attendance": {
            "get": {
                "tags": ["Reports"],
                "summary": "Generate attendance report",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "start_date",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "format": "date"}
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "format": "date"}
                    }
                ],
                "responses": {
                    "200": {"description": "Report generated"}
                }
            }
        },
        "/system/health": {
            "get": {
                "tags": ["System"],
                "summary": "Get system health status",
                "responses": {
                    "200": {
                        "description": "Health status retrieved",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SystemHealth"}
                            }
                        }
                    }
                }
            }
        },
        "/system/version": {
            "get": {
                "tags": ["System"],
                "summary": "Get system version",
                "responses": {
                    "200": {
                        "description": "Version info",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "version": {"type": "string"},
                                        "build": {"type": "string"},
                                        "environment": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


def setup_swagger(app: Flask, spec_path: str = "/api/swagger.json", 
                 swagger_ui_path: str = "/api/docs"):
    """
    Setup Swagger UI for Flask application
    
    Args:
        app: Flask application instance
        spec_path: Path to serve OpenAPI specification
        swagger_ui_path: Path to serve Swagger UI
    """
    logger = logging.getLogger(__name__)
    
    # Serve OpenAPI specification
    @app.route(spec_path)
    def swagger_spec():
        """Serve OpenAPI specification as JSON"""
        return jsonify(OPENAPI_SPEC)
    
    # Setup Swagger UI
    swaggerui_blueprint = get_swaggerui_blueprint(
        swagger_ui_path,
        spec_path,
        config={
            'app_name': "Neural Lens API Documentation",
            'layout': "BaseLayout",
            'deepLinking': True,
            'displayRequestDuration': True,
            'docExpansion': "none",
            'filter': True,
            'showExtensions': True,
            'showCommonExtensions': True
        }
    )
    
    app.register_blueprint(swaggerui_blueprint, url_prefix=swagger_ui_path)
    
    logger.info(f"Swagger UI available at: {swagger_ui_path}")
    logger.info(f"OpenAPI spec available at: {spec_path}")
    
    # Save specification to file
    try:
        spec_file = Path("docs/api/openapi.json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        with open(spec_file, 'w') as f:
            json.dump(OPENAPI_SPEC, f, indent=2)
        logger.info(f"OpenAPI specification saved to: {spec_file}")
    except Exception as e:
        logger.error(f"Failed to save OpenAPI spec: {e}")


# Decorator for API endpoints
def api_endpoint(tags: List[str] = None, summary: str = "", description: str = ""):
    """
    Decorator to add API documentation metadata to endpoints
    
    Usage:
        @app.route('/api/users')
        @api_endpoint(tags=['Users'], summary='Get all users')
        def get_users():
            return jsonify([])
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        
        # Store metadata for documentation generation
        decorated_function.api_tags = tags or []
        decorated_function.api_summary = summary
        decorated_function.api_description = description
        
        return decorated_function
    return decorator


if __name__ == "__main__":
    # Example usage
    from flask import Flask
    
    app = Flask(__name__)
    setup_swagger(app)
    
    print("API Documentation server running at http://localhost:5000/api/docs")
    app.run(debug=True)
