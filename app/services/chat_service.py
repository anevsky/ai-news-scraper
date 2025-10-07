"""
Chat Service - AI-Powered Article Q&A

This module provides chat functionality to answer questions about articles using Claude AI.

GenAI Integration - Anthropic Claude:
- Model: claude-sonnet-4-5-20250929
- Task: Answer questions about article content
- Capabilities:
  * Understand article context
  * Answer specific questions
  * Provide relevant quotes
  * Maintain conversation context

Responsibilities:
- Chat with users about article content
- Provide accurate answers based on article text
- Handle conversation history
- Track performance metrics

Design Pattern: Service Layer
- Encapsulates AI chat logic
- Manages conversation context
- Provides error handling
"""

import logging
from typing import List, Dict
from anthropic import Anthropic
import os

from app.repositories import ArticleRepository

logger = logging.getLogger(__name__)

# Maximum tokens for Claude response
MAX_RESPONSE_TOKENS = 2_000


class ChatService:
    """
    Service for AI-powered chat about articles using Claude.

    This service allows users to ask questions about analyzed articles
    and get intelligent responses based on the article content.

    GenAI Technology: Anthropic Claude Sonnet 4.5
    - Purpose: Answer questions about article content
    - Model: claude-sonnet-4-5-20250929
    - Input: Article content + user question + chat history
    - Output: Relevant answer based on article

    Key Features:
    1. Context-Aware Responses: Uses full article content
    2. Conversation History: Maintains context across messages
    3. Accurate Answers: Grounded in article text
    4. Citation Support: Can quote relevant parts
    """

    def __init__(self):
        """Initialize chat service with Claude client and repositories."""
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.article_repo = ArticleRepository()

    def chat(
        self,
        article_id: int,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Chat with Claude about an article.

        Args:
            article_id: ID of the article to discuss
            user_message: User's question or message
            conversation_history: Previous messages in conversation (optional)
                Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            Dictionary with:
            - response: Claude's answer
            - tokens: Number of tokens used

        Raises:
            ValueError: If article not found or not analyzed
            Exception: If Claude API call fails
        """
        # Get article from database
        article = self.article_repo.get_by_id(article_id)

        if not article:
            raise ValueError(f"Article {article_id} not found")

        if not article.get("has_analysis"):
            raise ValueError("Article has not been analyzed yet. Please analyze it first.")

        # Build conversation messages
        messages = []

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        # Build system prompt with article context
        system_prompt = f"""You are a helpful assistant that answers questions about news articles.

Article Title: {article.get('title', 'Unknown')}
Author: {article.get('author', 'Unknown')}
Source: {article.get('source_domain', 'Unknown')}

Article Content:
{article.get('content', '')}

Article Summary:
{article.get('summary', 'No summary available')}

Topics: {', '.join(article.get('topics', []))}

Instructions:
- Answer questions based ONLY on the article content above
- Be concise and accurate
- Quote relevant parts when helpful
- If the answer is not in the article, say so clearly
- If the answer is not in the article, provide answer from your sources or knowledge, but mention that explicitly
- Be conversational and friendly
"""

        try:
            # Call Claude API
            logger.info(f"Sending chat request for article {article_id}")

            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=MAX_RESPONSE_TOKENS,
                system=system_prompt,
                messages=messages
            )

            # Extract response text
            assistant_message = response.content[0].text

            # Track token usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            logger.info(f"Chat response generated: {total_tokens} tokens")

            return {
                "response": assistant_message,
                "tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            logger.error(f"Error in chat: {e}")
            raise Exception(f"Failed to get chat response: {str(e)}")
