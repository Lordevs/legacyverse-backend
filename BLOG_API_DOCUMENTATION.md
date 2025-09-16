# Blog API Documentation

This document provides comprehensive information about the Blog API endpoints for the LegacyVerse application.

## Overview

The Blog API provides functionality for:
- Creating, reading, updating, and deleting blog posts
- Managing comments on blog posts
- Liking and saving blog posts
- AI-powered blog generation and rewriting
- User-specific blog management

## Authentication

Most endpoints require JWT authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your-jwt-token>
```

## Base URL
```
http://localhost:8000/api/
```

## Models

### Blog
- `id`: UUID (primary key)
- `title`: CharField (max 200 characters)
- `content`: TextField
- `author`: ForeignKey to User
- `status`: ChoiceField ('draft' or 'public')
- `content_source`: ChoiceField ('user_written', 'ai_generated', 'ai_rewritten')
- `ai_prompt`: TextField (optional, for AI-generated content)
- `slug`: SlugField (auto-generated from title)
- `excerpt`: TextField (max 300 characters, optional)
- `tags`: CharField (comma-separated, max 500 characters)
- `created_at`: DateTimeField
- `updated_at`: DateTimeField
- `published_at`: DateTimeField (set when status becomes 'public')

### Comment
- `id`: UUID (primary key)
- `blog`: ForeignKey to Blog
- `author`: ForeignKey to User
- `content`: TextField
- `parent_comment`: ForeignKey to Comment (for replies)
- `is_approved`: BooleanField (default: True)
- `is_edited`: BooleanField (default: False)
- `created_at`: DateTimeField
- `updated_at`: DateTimeField

### Like
- `id`: UUID (primary key)
- `blog`: ForeignKey to Blog
- `user`: ForeignKey to User
- `is_liked`: BooleanField (default: True)
- `created_at`: DateTimeField
- `updated_at`: DateTimeField

### SavedBlog
- `id`: UUID (primary key)
- `blog`: ForeignKey to Blog
- `user`: ForeignKey to User
- `created_at`: DateTimeField

## Endpoints

### Blog Endpoints

#### 1. List Blogs
```
GET /api/blogs/
```

**Query Parameters:**
- `author`: Filter by author ID
- `status`: Filter by status ('draft' or 'public')
- `tags`: Filter by tags (comma-separated)
- `search`: Search in title, content, excerpt, and tags
- `page`: Page number for pagination

**Response:**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/blogs/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "title": "Blog Title",
      "excerpt": "Blog excerpt...",
      "author": {
        "id": "uuid",
        "fullname": "Author Name",
        "email": "author@example.com",
        "username": "author123"
      },
      "status": "public",
      "content_source": "user_written",
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:00:00Z",
      "published_at": "2024-01-01T12:00:00Z",
      "slug": "blog-title",
      "tags": "technology,programming",
      "comments_count": 5,
      "likes_count": 10
    }
  ]
}
```

#### 2. Create Blog
```
POST /api/blogs/
```

**Authentication:** Required

**Request Body:**
```json
{
  "title": "My New Blog Post",
  "content": "This is the content of my blog post...",
  "status": "draft",
  "content_source": "user_written",
  "excerpt": "A brief description of the blog post",
  "tags": "technology,programming,django"
}
```

**Response:**
```json
{
  "id": "uuid",
  "title": "My New Blog Post",
  "content": "This is the content of my blog post...",
  "author": {
    "id": "uuid",
    "fullname": "Your Name",
    "email": "your@email.com",
    "username": "yourusername"
  },
  "status": "draft",
  "content_source": "user_written",
  "ai_prompt": null,
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z",
  "published_at": null,
  "slug": "my-new-blog-post",
  "excerpt": "A brief description of the blog post",
  "tags": "technology,programming,django",
  "comments_count": 0,
  "likes_count": 0,
  "is_liked_by_user": false,
  "is_saved_by_user": false,
  "comments": []
}
```

#### 3. Get Blog Detail
```
GET /api/blogs/{id}/
```

**Response:** Same as create blog response

#### 4. Update Blog
```
PUT /api/blogs/{id}/
PATCH /api/blogs/{id}/
```

**Authentication:** Required (author only)

**Request Body:**
```json
{
  "title": "Updated Blog Title",
  "content": "Updated content...",
  "status": "public",
  "excerpt": "Updated excerpt",
  "tags": "updated,tags"
}
```

#### 5. Delete Blog
```
DELETE /api/blogs/{id}/
```

**Authentication:** Required (author only)

#### 6. Like/Unlike Blog
```
POST /api/blogs/{id}/like/
```

**Authentication:** Required

**Response:**
```json
{
  "is_liked": true,
  "likes_count": 11
}
```

#### 7. Save/Unsave Blog
```
POST /api/blogs/{id}/save/
```

**Authentication:** Required

**Response:**
```json
{
  "is_saved": true
}
```

#### 8. Track Blog View
```
GET /api/blogs/{id}/track_view/
```

**Authentication:** Required

**Response:**
```json
{
  "viewed": true
}
```

### Comment Endpoints

#### 1. List Comments for a Blog
```
GET /api/blogs/{blog_id}/comments/
```

**Response:**
```json
[
  {
    "id": "uuid",
    "content": "This is a great blog post!",
    "author": {
      "id": "uuid",
      "fullname": "Commenter Name",
      "email": "commenter@example.com",
      "username": "commenter123"
    },
    "parent_comment": null,
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z",
    "is_approved": true,
    "is_edited": false,
    "replies_count": 2
  }
]
```

#### 2. Create Comment
```
POST /api/blogs/{blog_id}/comments/
```

**Authentication:** Required

**Request Body:**
```json
{
  "content": "This is my comment on the blog post",
  "parent_comment": "uuid" // Optional, for replies
}
```

#### 3. Update Comment
```
PUT /api/blogs/{blog_id}/comments/{comment_id}/
PATCH /api/blogs/{blog_id}/comments/{comment_id}/
```

**Authentication:** Required (author only)

#### 4. Delete Comment
```
DELETE /api/blogs/{blog_id}/comments/{comment_id}/
```

**Authentication:** Required (author only)

### AI Generation Endpoints

#### 1. Generate AI Blog
```
POST /api/ai/generate-blog/
```

**Authentication:** Required

**Request Body:**
```json
{
  "prompt": "Write a blog post about the benefits of using Django for web development",
  "title": "Optional Title", // Optional
  "content_source": "ai_generated" // or "ai_rewritten"
}
```

**Response:**
```json
{
  "title": "The Benefits of Using Django for Web Development",
  "content": "Django is a powerful web framework...",
  "content_source": "ai_generated",
  "ai_prompt": "Write a blog post about the benefits of using Django for web development"
}
```

### User-Specific Endpoints

#### 1. Get User's Blogs
```
GET /api/user/blogs/
```

**Authentication:** Required

**Response:** Array of blog objects (same as blog list)

#### 2. Get User's Saved Blogs
```
GET /api/user/saved-blogs/
```

**Authentication:** Required

**Response:**
```json
[
  {
    "id": "uuid",
    "blog": {
      // Full blog object
    },
    "user": {
      // User object
    },
    "created_at": "2024-01-01T12:00:00Z"
  }
]
```

### SEO-Friendly URLs

#### 1. Get Blog by Slug
```
GET /blog/{slug}/
```

**Example:** `GET /blog/my-awesome-blog-post/`

**Response:** Same as blog detail response

## Error Responses

### 400 Bad Request
```json
{
  "field_name": ["Error message"]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 500 Internal Server Error
```json
{
  "error": "Failed to generate content. Please try again."
}
```

## Rate Limiting

The API implements rate limiting for AI generation endpoints to prevent abuse.

## Environment Variables

Make sure to set the following environment variables:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

## Examples

### Creating a Blog with AI Generation

1. First, generate content using AI:
```bash
curl -X POST http://localhost:8000/api/ai/generate-blog/ \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write about the future of artificial intelligence",
    "content_source": "ai_generated"
  }'
```

2. Then create a blog with the generated content:
```bash
curl -X POST http://localhost:8000/api/blogs/ \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "The Future of Artificial Intelligence",
    "content": "Generated content here...",
    "status": "draft",
    "content_source": "ai_generated",
    "ai_prompt": "Write about the future of artificial intelligence"
  }'
```

### Searching Blogs

```bash
curl "http://localhost:8000/api/blogs/?search=django&tags=programming&status=public"
```

### Getting User's Drafts

```bash
curl -H "Authorization: Bearer <your-token>" \
  "http://localhost:8000/api/user/blogs/?status=draft"
```

## Notes

- All timestamps are in UTC format
- UUIDs are used for all primary keys
- Pagination is enabled for list endpoints (20 items per page)
- Comments support threading (replies to comments)
- Blog views are tracked for analytics
- AI generation requires a valid OpenAI API key
- Draft blogs are only visible to their authors
- Public blogs are visible to everyone
