从帖子中抽取招聘信息。只抽取原文明确提供的信息，未知字段返回 null，保留 evidence。

输出必须符合 Recruitment schema。不要混淆帖子 URL 和官方投递链接；帖子链接放 source_url，官方投递链接放 official_url。

