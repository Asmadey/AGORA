"use server";

export async function fetchRealNews() {
  try {
    const rssUrl = "https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru";
    const res = await fetch(rssUrl, { next: { revalidate: 3600 } });
    if (!res.ok) {
      throw new Error("Failed to fetch RSS");
    }
    const text = await res.text();
    
    // Very simple RSS parsing using regex so we don't need external libraries
    const items: Array<{title: string, source: string, summary: string}> = [];
    const itemRegex = /<item>([\s\S]*?)<\/item>/g;
    let match;
    let count = 0;
    while ((match = itemRegex.exec(text)) !== null && count < 10) {
      const itemHtml = match[1];
      const titleMatch = /<title>(.*?)<\/title>/.exec(itemHtml);
      const sourceMatch = /<source.*?>(.*?)<\/source>/.exec(itemHtml);
      
      if (titleMatch) {
        items.push({
          title: titleMatch[1].replace(/<!\[CDATA\[(.*?)\]\]>/, '$1'),
          source: sourceMatch ? sourceMatch[1] : "Google News",
          summary: ""
        });
        count++;
      }
    }
    
    return items;
  } catch (error) {
    console.error("Error fetching news:", error);
    return [];
  }
}
