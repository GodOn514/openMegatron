---
name: bilibili_search
description: Search Bilibili videos, video details, user info, popular videos, and hot search terms through public endpoints.
category: media
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: One of search, video, user, popular, hot_search.
    query:
      type: string
      description: Search keyword for action=search.
    bvid:
      type: string
      description: Bilibili video id for action=video.
    mid:
      type: integer
      description: User id for action=user.
    count:
      type: integer
      description: Result count.
    page:
      type: integer
      description: Search page.
    order:
      type: string
      description: Search order, such as totalrank, click, pubdate.
  required:
    - action
keywords: [bilibili, b站, video, media, search, hot_search]
---

# Bilibili Search

Media-category skill for Bilibili discovery and metadata lookup.
