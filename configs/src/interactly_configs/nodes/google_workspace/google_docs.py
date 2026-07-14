from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
    NodeType,
)

class GoogleWorkspaceOAuth2Credentials(BaseModel):
    """Configuration for Google Workspace OAuth2 credentials."""

    type: Literal["google_workspace_oauth2"] = Field(
        default="google_workspace_oauth2",
        description="Type of the credentials. Must be 'google_workspace_oauth2'",
        title="Credentials Type",
    )
    oauth_redirect_uri: Optional[str] = Field(
        None,
        description="OAuth redirect URI for Google Workspace. If not provided, the default value at os.environ['GOOGLE_OAUTH_REDIRECT_URI'] will be used.",
        title="OAuth Redirect URI",
    )
    client_id: Optional[str] = Field(
        None,
        description="Client ID for Google Workspace. If not provided, the default value at os.environ['GOOGLE_CLIENT_ID'] will be used.",
        title="Client ID",
    )
    client_secret: Optional[str] = Field(
        None,
        description="Client Secret for Google Workspace. If not provided, the default value at os.environ['GOOGLE_CLIENT_SECRET'] will be used.",
        title="Client Secret",
    )

    model_config = ConfigDict(
        title="OAuth2 Credentials",
    )

class GoogleWorkspaceServiceAccountCredentials(BaseModel):
    """Configuration for Google Workspace service account credentials."""

    type: Literal["google_workspace_service_account"] = Field(
        default="google_workspace_service_account",
        description="Type of the credentials. Must be 'google_workspace_service_account'",
        title="Credentials Type",
    )
    service_account_email: Optional[str] = Field(
        None,
        description="Service account email for Google Workspace. If not provided, the default value at os.environ['GOOGLE_SERVICE_ACCOUNT_EMAIL'] will be used.",
        title="Service Account Email",
    )
    private_key_id: Optional[str] = Field(
        None,
        description="Private key ID for Google Workspace. If not provided, the default value at os.environ['GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID'] will be used.",
        title="Private Key ID",
    )
    private_key: Optional[str] = Field(
        None,
        description="Private key for Google Workspace. If not provided, the default value at os.environ['GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY'] will be used.",
        title="Private Key",
    )
    impersonation_email: Optional[str] = Field(
        None,
        description="Email to impersonate for Google Workspace. If not provided, the default value at os.environ['GOOGLE_SERVICE_ACCOUNT_IMPERSONATION_EMAIL'] will be used.",
        title="Impersonation Email",
    )

    model_config = ConfigDict(
        title="Service Account Credentials",
    )

class GoogleWorkspaceAPIKeyCredentials(BaseModel):
    """Configuration for Google Workspace API Key credentials."""

    type: Literal["google_workspace_api_key"] = Field(
        default="google_workspace_api_key",
        description="Type of the credentials. Must be 'google_workspace_api_key'",
        title="Credentials Type",
    )
    api_key: Optional[str] = Field(
        None,
        description="API Key for Google Workspace, used to access public APIs. If not provided, the default value at os.environ['GOOGLE_API_KEY'] will be used.",
        title="API Key",
    )

    model_config = ConfigDict(
        title="API Key Credentials",
    )

GoogleWorkspaceCredentials = Annotated[
    Union[GoogleWorkspaceOAuth2Credentials, GoogleWorkspaceServiceAccountCredentials, GoogleWorkspaceAPIKeyCredentials],
    Field(discriminator="type"),
]

### Google Docs CREATE ###

class GoogleDocsCreateDocumentConfig(BaseModel):
    """Configuration for creating a Google Docs document."""

    type: Literal["google_docs_create_document"] = Field(
        default="google_docs_create_document",
        description="Type of the node. Must be 'google_docs_create_document'",
        title="Node Type",
    )
    title: Optional[str] = Field(
        None,
        description="Title of the Google Docs document to be created.",
        title="Document Title",
    )
    drive_name_or_id: Optional[str] = Field(
        None,
        description="Name or ID of the Google Drive where the document will be created. If not provided, the document will be created in the user's default drive.",
        title="Drive Name or ID",
    )
    folder_name_or_id: Optional[str] = Field(
        None,
        description="Name or ID of the folder where the document will be created. If not provided, the document will be created in the root of the drive.",
        title="Folder Name or ID",
    )

    model_config = ConfigDict(
        title="Google Docs Create Document Node",
    )

class GoogleDocsCreateDocumentNodeRunInput(BaseModel):
    """Run input for creating a Google Docs document."""

    type: Literal["google_docs_create_document"] = Field(
        default="google_docs_create_document",
        description="Type of the node. Must be 'google_docs_create_document'",
        title="Node Type",
    )

class GoogleDocsCreateDocumentNodeRunOutput(BaseModel):
    """Run output for creating a Google Docs document."""

    type: Literal["google_docs_create_document"] = Field(
        default="google_docs_create_document",
        description="Type of the node. Must be 'google_docs_create_document'",
        title="Node Type",
    )
    document_id: Optional[str] = Field(
        None,
        description="ID of the created Google Docs document.",
        title="Document ID",
    )
    document_url: Optional[str] = Field(
        None,
        description="URL of the created Google Docs document.",
        title="Document URL",
    )

### Google Docs GET ###

class GoogleDocsGetDocumentConfig(BaseModel):
    """Configuration for getting a Google Docs document."""

    type: Literal["google_docs_get_document"] = Field(
        default="google_docs_get_document",
        description="Type of the node. Must be 'google_docs_get_document'",
        title="Node Type",
    )
    document_id_or_url: Optional[str] = Field(
        None,
        description="ID or URL of the Google Docs document to be retrieved.",
        title="Document ID or URL",
    )
    return_full_model: bool = Field(
        default=False,
        description="Whether to return the full document model or just the plain text content.",
        title="Return Full Model",
    )

    model_config = ConfigDict(
        title="Google Docs Get Document Node",
    )

class GoogleDocsGetDocumentNodeRunInput(BaseModel):
    """Run input for getting a Google Docs document."""

    type: Literal["google_docs_get_document"] = Field(
        default="google_docs_get_document",
        description="Type of the node. Must be 'google_docs_get_document'",
        title="Node Type",
    )

class GoogleDocsGetDocumentNodeRunOutput(BaseModel):
    """Run output for getting a Google Docs document."""

    type: Literal["google_docs_get_document"] = Field(
        default="google_docs_get_document",
        description="Type of the node. Must be 'google_docs_get_document'",
        title="Node Type",
    )
    document_content: Optional[Any] = Field(
        None,
        description="Content of the retrieved Google Docs document.",
        title="Document Content",
    )

### Google Docs UPDATE ###

class GoogleDocsUpdateWithTextConfig(BaseModel):
    """Configuration for updating a Google Docs document with text."""

    type: Literal["google_docs_update_with_text"] = Field(
        default="google_docs_update_with_text",
        description="Type of the node. Must be 'google_docs_update_with_text'",
        title="Node Type",
    )
    content: Optional[str] = Field(
        None,
        description="Content to update the Google Docs document with.",
        title="Document Content",
    )
    insert_index: Optional[int] = Field(
        None,
        description="Index at which to insert the content in the Google Docs document. If not provided, the content will be appended to the end of the document.",
        title="Insert Index",
    )

    model_config = ConfigDict(
        title="Google Docs Update With Text Node",
    )

GoogleDocsUpdateObject = Annotated[Union[GoogleDocsUpdateWithTextConfig], Field(discriminator="type")]

class GoogleDocsUpdateDocumentConfig(BaseModel):
    """Configuration for updating a Google Docs document."""

    type: Literal["google_docs_update_document"] = Field(
        default="google_docs_update_document",
        description="Type of the node. Must be 'google_docs_update_document'",
        title="Node Type",
    )
    document_id_or_url: Optional[str] = Field(
        None,
        description="ID or URL of the Google Docs document to be updated.",
        title="Document ID or URL",
    )
    updates: Optional[GoogleDocsUpdateObject] = Field(
        default=None,
        description="Updates to be applied to the Google Docs document. If not provided, no updates will be made.",
        title="Document Updates",
    )

    model_config = ConfigDict(
        title="Google Docs Update Document Node",
    )

class GoogleDocsUpdateDocumentNodeRunInput(BaseModel):
    """Run input for updating a Google Docs document."""

    type: Literal["google_docs_update_document"] = Field(
        default="google_docs_update_document",
        description="Type of the node. Must be 'google_docs_update_document'",
        title="Node Type",
    )

class GoogleDocsUpdateDocumentNodeRunOutput(BaseModel):
    """Run output for updating a Google Docs document."""

    type: Literal["google_docs_update_document"] = Field(
        default="google_docs_update_document",
        description="Type of the node. Must be 'google_docs_update_document'",
        title="Node Type",
    )
    document_id: Optional[str] = Field(
        None,
        description="ID of the updated Google Docs document.",
        title="Document ID",
    )
    document_url: Optional[str] = Field(
        None,
        description="URL of the updated Google Docs document.",
        title="Document URL",
    )

##################################################

GoogleDocsOperateDocumentConfig = Annotated[
    Union[GoogleDocsCreateDocumentConfig, GoogleDocsGetDocumentConfig, GoogleDocsUpdateDocumentConfig],
    Field(discriminator="type"),
]

class GoogleDocsNodeConfig(BaseNodeConfig):
    type: Literal["google_docs"] = Field(
        default=NodeType.GOOGLE_DOCS.value,
        description="Type of the node. Must be 'google_docs'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.GOOGLE_WORKSPACE.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.GOOGLE_DOCS.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    credentials: Optional[GoogleWorkspaceCredentials] = Field(
        default=None,
        description="Credentials for Google Workspace. If not provided, the default credentials will be used.",
        title="Google Workspace Credentials",
    )
    operate_document: Optional[GoogleDocsOperateDocumentConfig] = Field(
        default=None,
        description="Configuration for operating on a Google Docs document (create, get, or update).",
        title="Document Operation",
    )

    model_config = ConfigDict(
        title="Google Docs Node",
    )

GoogleDocsOperateRunInput = Annotated[
    Union[
        GoogleDocsCreateDocumentNodeRunInput, GoogleDocsGetDocumentNodeRunInput, GoogleDocsUpdateDocumentNodeRunInput
    ],
    Field(discriminator="type"),
]

class GoogleDocsNodeRunInput(BaseNodeRunInput):
    """Run input for Google Docs node."""

    type: Literal["google_docs"] = Field(
        default="google_docs",
        description="Type of the node. Must be 'google_docs'",
        title="Node Type",
    )
    operate_document: Optional[GoogleDocsOperateRunInput] = Field(
        default=None,
        description="Configuration for operating on a Google Docs document (create, get, or update).",
        title="Document Operation",
    )

    model_config = ConfigDict(
        title="Google Docs Node",
    )

GoogleDocsOperateRunOutput = Annotated[
    Union[
        GoogleDocsCreateDocumentNodeRunOutput, GoogleDocsGetDocumentNodeRunOutput, GoogleDocsUpdateDocumentNodeRunOutput
    ],
    Field(discriminator="type"),
]

class GoogleDocsNodeRunOutput(BaseNodeRunOutput):
    """Run output for Google Docs node."""

    type: Literal["google_docs"] = Field(
        default="google_docs",
        description="Type of the node. Must be 'google_docs'",
        title="Node Type",
    )
    operate_document: Optional[GoogleDocsOperateRunOutput] = Field(
        default=None,
        description="Output from operating on a Google Docs document (create, get, or update).",
        title="Document Operation Output",
    )
