from enum import Enum
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
    NodeType,
)


class HttpMethodEnum(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class BodyContentTypeEnum(str, Enum):
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    MULTIPART = "multipart/form-data"
    TEXT = "text/plain"

class ResponseFormatEnum(str, Enum):
    JSON = "json"
    TEXT = "text"
    BINARY = "binary"

class HttpRequestNodeConfig(BaseNodeConfig):
    type: Literal["http_request"] = Field(
        default=NodeType.HTTP_REQUEST.value,
        description="Type of the node. Must be 'http_request'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.REST_API.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.HTTP_REQUEST.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    url: Optional[str] = Field(
        default=None,
        description="The URL to send the HTTP request to",
        title="HTTP Request URL",
    )
    method: Optional[HttpMethodEnum] = Field(
        default=HttpMethodEnum.GET,
        description="HTTP method to use (GET, POST, PUT, PATCH, DELETE, etc.)",
        title="HTTP Method",
    )
    headers: Optional[dict] = Field(
        default=None,
        description="Optional HTTP headers as a dictionary",
        title="Headers",
    )
    query_parameters: Optional[str] = Field(
        default=None,
        description="Query parameters as a dictionary",
        title="Query Parameters",
    )
    body_parameters: Optional[str] = Field(
        default=None,
        description="Body parameters as a dictionary (for POST, PUT, PATCH)",
        title="Body Parameters",
    )
    body_content_type: Optional[BodyContentTypeEnum] = Field(
        default=BodyContentTypeEnum.JSON,
        description="Content-Type for the request body (e.g., application/json, form-data)",
        title="Body Content-Type",
    )
    timeout: Optional[int] = Field(
        default=30,
        description="Timeout for the HTTP request in seconds",
        title="Timeout (seconds)",
        ge=0,
        le=300,
    )
    response_format: Optional[ResponseFormatEnum] = Field(
        default=ResponseFormatEnum.JSON,
        description="Expected response format (json, text, binary)",
        title="Response Format",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="http_request_result",
        description="Name of the runtime variable to store the result",
        title="Result Runtime Variable Name",
    )

    model_config = ConfigDict(
        title="HTTP Request Node",
    )

class HttpRequestNodeRunInput(BaseNodeRunInput):
    type: Literal["http_request"] = Field(
        default="http_request", description="Discriminator field which must always be 'http_request'"
    )
    override_url: Optional[str] = Field(
        default=None,
        description="Override the URL for the HTTP request",
        title="Override URL",
    )

class HttpRequestNodeRunOutput(BaseNodeRunOutput):
    type: Literal["http_request"] = Field(
        default="http_request", description="Discriminator field which must always be 'http_request'"
    )
    curl_command: Optional[str] = Field(
        default=None,
        description="The curl command that was executed",
        title="Curl Command",
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the HTTP request was successful",
        title="HTTP Request Successful",
    )
    http_status_code: Optional[int] = Field(
        default=None,
        description="HTTP status code returned by the request",
        title="HTTP Status Code",
    )
    http_response: Optional[dict] = Field(
        default=None,
        description="HTTP response data",
        title="HTTP Response",
    )
