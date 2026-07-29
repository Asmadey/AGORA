"use server";

export async function fetchVideoMetadata(url: string) {
  try {
    // Basic oEmbed endpoint to get video metadata for popular services (YouTube, Vimeo, etc)
    const oembedUrl = `https://noembed.com/embed?url=${encodeURIComponent(url)}`;
    const res = await fetch(oembedUrl, { next: { revalidate: 3600 } });
    if (!res.ok) {
      return null;
    }
    const data = await res.json();
    if (data.error) return null;
    return {
      title: data.title || null,
      author_name: data.author_name || null,
      provider: data.provider_name || null,
    };
  } catch (error) {
    console.error("Error fetching video metadata:", error);
    return null;
  }
}
