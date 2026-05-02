
"""
Pydantic models for Gemini Generative Language API v1beta.

Defines data schemas for requests and responses compatible with
Google's Gemini API specification.

Reference: https://ai.google.dev/api/generate-content
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


# ==================================================================================================
# Part Models
# ==================================================================================================


class GeminiTextPart(BaseModel):
    """
    Text content part in Gemini format.

    Attributes:
        text: The text content.
    """

    text: str


class GeminiFunctionCallPart(BaseModel):
    """
    Function call part in Gemini format.

    Represents a tool call made by the model.

    Attributes:
        functionCall: Dict containing 'name' (str) and 'args' (dict).
    """

    functionCall: Dict[str, Any]


class GeminiFunctionResponsePart(BaseModel):
    """
    Function response part in Gemini format.

    Represents the result of a tool call, sent by the user.

    Attributes:
        functionResponse: Dict containing 'name' (str) and 'response' (dict).
    """

    functionResponse: Dict[str, Any]


class GeminiInlineDataPart(BaseModel):
    """
    Inline data (image) part in Gemini format.

    Attributes:
        inlineData: Dict containing 'mimeType' (str) and 'data' (str, base64-encoded).
    """

    inlineData: Dict[str, Any]


# Union type for all part variants. Dict[str, Any] is the catch-all for unknown parts.
GeminiPart = Union[
    GeminiTextPart,
    GeminiFunctionCallPart,
    GeminiFunctionResponsePart,
    GeminiInlineDataPart,
    Dict[str, Any],
]


# ==================================================================================================
# Content Model
# ==================================================================================================


class GeminiContent(BaseModel):
    """
    Content block in Gemini format.

    Represents a single turn in the conversation.

    Attributes:
        role: Message role ('user' or 'model'). None is treated as 'user'.
        parts: List of content parts.
    """

    role: Optional[str] = None
    parts: List[GeminiPart]


# ==================================================================================================
# Tool Models
# ==================================================================================================


class GeminiFunctionDeclaration(BaseModel):
    """
    Function declaration for a Gemini tool.

    Attributes:
        name: Function name.
        description: Human-readable description of the function.
        parameters: JSON Schema for function parameters.
    """

    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class GeminiTool(BaseModel):
    """
    Tool definition in Gemini format.

    Attributes:
        functionDeclarations: List of function declarations available to the model.
    """

    functionDeclarations: Optional[List[GeminiFunctionDeclaration]] = None


# ==================================================================================================
# Generation Config
# ==================================================================================================


class GeminiGenerationConfig(BaseModel):
    """
    Generation configuration for Gemini API.

    Attributes:
        temperature: Sampling temperature.
        topP: Top-p sampling parameter.
        topK: Top-k sampling parameter.
        maxOutputTokens: Maximum number of output tokens.
        stopSequences: Custom stop sequences.
        candidateCount: Number of response candidates to generate.
    """

    temperature: Optional[float] = None
    topP: Optional[float] = None
    topK: Optional[int] = None
    maxOutputTokens: Optional[int] = None
    stopSequences: Optional[List[str]] = None
    candidateCount: Optional[int] = None


# ==================================================================================================
# Request Model
# ==================================================================================================


class GeminiGenerateContentRequest(BaseModel):
    """
    Request to Gemini generateContent API.

    Attributes:
        contents: List of conversation turns.
        tools: List of available tools.
        systemInstruction: System instruction content block.
        generationConfig: Generation configuration parameters.
    """

    contents: List[GeminiContent]
    tools: Optional[List[GeminiTool]] = None
    systemInstruction: Optional[GeminiContent] = None
    generationConfig: Optional[GeminiGenerationConfig] = None

    model_config = {"extra": "allow"}  # Gemini has many optional fields


# ==================================================================================================
# Response Models
# ==================================================================================================


class GeminiCandidate(BaseModel):
    """
    A single response candidate from Gemini API.

    Attributes:
        content: The generated content.
        finishReason: Why generation stopped (e.g., 'STOP', 'MAX_TOKENS').
        index: Candidate index.
    """

    content: Optional[GeminiContent] = None
    finishReason: Optional[str] = None
    index: Optional[int] = None


class GeminiUsageMetadata(BaseModel):
    """
    Token usage metadata in Gemini format.

    Attributes:
        promptTokenCount: Number of tokens in the prompt.
        candidatesTokenCount: Number of tokens in the response candidates.
        totalTokenCount: Total token count.
    """

    promptTokenCount: Optional[int] = None
    candidatesTokenCount: Optional[int] = None
    totalTokenCount: Optional[int] = None


class GeminiGenerateContentResponse(BaseModel):
    """
    Response from Gemini generateContent API.

    Attributes:
        candidates: List of response candidates.
        usageMetadata: Token usage information.
        modelVersion: Model version used for generation.
    """

    candidates: Optional[List[GeminiCandidate]] = None
    usageMetadata: Optional[GeminiUsageMetadata] = None
    modelVersion: Optional[str] = None


# ==================================================================================================
# Model Info Models (for /v1beta/models endpoint)
# ==================================================================================================


class GeminiModelInfo(BaseModel):
    """
    Model information in Gemini format.

    Attributes:
        name: Full model resource name (e.g., 'models/gemini-2.5-pro').
        displayName: Human-readable model name.
        supportedGenerationMethods: List of supported API methods.
    """

    name: str
    displayName: str
    supportedGenerationMethods: List[str]

    model_config = {"extra": "allow"}


class GeminiModelsListResponse(BaseModel):
    """
    Response from Gemini /v1beta/models list endpoint.

    Attributes:
        models: List of available models.
    """

    models: List[GeminiModelInfo]
