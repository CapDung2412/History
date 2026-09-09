"use client";

import { useMemo, useState } from "react";
import { CheckIcon } from "@/components/icons";
import { TtsControls } from "@/components/tts-controls";
import { toAssetUrl } from "@/lib/api";
import { formatCategory, formatPeriod } from "@/lib/format";
import type { Artifact, ArtifactImage, ArtifactStory } from "@/lib/types";

type StoryLevel = "quick" | "overview" | "deep";

interface StoryExplorerProps {
  artifact: Artifact;
  story: ArtifactStory;
}

const TABS: Array<{ id: StoryLevel; label: string; duration: string }> = [
  { id: "quick", label: "Nhìn nhanh", duration: "10 giây" },
  { id: "overview", label: "Câu chuyện", duration: "1 phút" },
  { id: "deep", label: "Khám phá sâu", duration: "Đầy đủ" },
];

export function StoryExplorer({ artifact, story }: StoryExplorerProps) {
  return <StoryContent key={artifact.item_id} artifact={artifact} story={story} />;
}

function StoryContent({ artifact, story }: StoryExplorerProps) {
  const [level, setLevel] = useState<StoryLevel>("quick");

  const narration = useMemo(
    () =>
      Array.from(new Set([
        story.quick.title,
        formatPeriod(story.quick.period, story.quick.year),
        story.overview.description,
        story.overview.what_it_is,
        story.overview.role,
        story.overview.context,
        story.overview.significance,
        ...(story.overview.paragraphs || []),
        story.deep.description,
        story.deep.event,
      ].filter(Boolean)))
        .join(". "),
    [story],
  );

  return (
    <section className="story-section" aria-labelledby="story-title">
      <div className="story-header">
        <div>
          <p className="eyebrow">Câu chuyện hiện vật</p>
          <h2 id="story-title">Khám phá theo nhịp của em</h2>
        </div>
        <span className="verified-chip">
          <CheckIcon /> Dữ liệu từ kho hiện vật
        </span>
      </div>

      <div className="story-tabs" role="tablist" aria-label="Mức độ nội dung">
        {TABS.map((tab) => (
          <button
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
            aria-selected={level === tab.id}
            tabIndex={level === tab.id ? 0 : -1}
            className={level === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => setLevel(tab.id)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const current = TABS.findIndex((item) => item.id === level);
              const direction = event.key === "ArrowRight" ? 1 : -1;
              const next = event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : (current + direction + TABS.length) % TABS.length;
              setLevel(TABS[next].id);
              document.getElementById(`tab-${TABS[next].id}`)?.focus();
            }}
          >
            <span>{tab.label}</span>
            <small>{tab.duration}</small>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`panel-${level}`}
        aria-labelledby={`tab-${level}`}
        tabIndex={0}
        className="story-panel"
      >
        {level === "quick" && <QuickStory artifact={artifact} story={story} />}
        {level === "overview" && <OverviewStory story={story} />}
        {level === "deep" && <DeepStory artifact={artifact} story={story} />}
      </div>

      <TtsControls text={narration} contentId={artifact.item_id} />
    </section>
  );
}

function QuickStory({
  artifact,
  story,
}: {
  artifact: Artifact;
  story: ArtifactStory;
}) {
  const image = story.quick.image || artifact.images[0];
  return (
    <div className="quick-story">
      <StoryImage image={image} name={artifact.name} featured />
      <div className="quick-story-content">
        <span className="story-level-label">Trong 10 giây</span>
        <h3>{story.quick.title || artifact.name}</h3>
        <dl className="artifact-facts">
          <div>
            <dt>Loại tư liệu</dt>
            <dd>{formatCategory(story.quick.category || artifact.category)}</dd>
          </div>
          <div>
            <dt>Giai đoạn</dt>
            <dd>
              {formatPeriod(
                story.quick.period || artifact.historical_period,
                story.quick.year ?? artifact.year,
              )}
            </dd>
          </div>
          {artifact.location?.city && (
            <div>
              <dt>Nơi lưu giữ</dt>
              <dd>{artifact.location.city}</dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}

function OverviewStory({ story }: { story: ArtifactStory }) {
  const overview = story.overview;
  const hasStructured =
    overview.what_it_is || overview.role || overview.context || overview.significance;
  return (
    <div className="overview-story">
      <span className="story-level-label">Câu chuyện khoảng 1 phút</span>
      {overview.description && <p className="story-intro">{overview.description}</p>}
      {hasStructured ? (
        <div className="story-point-grid">
          {overview.what_it_is && (
            <StoryPoint number="01" title="Hiện vật là gì?" text={overview.what_it_is} />
          )}
          {overview.role && (
            <StoryPoint number="02" title="Vai trò và công dụng" text={overview.role} />
          )}
          {overview.context && (
            <StoryPoint number="03" title="Bối cảnh lịch sử" text={overview.context} />
          )}
          {overview.significance && (
            <StoryPoint number="04" title="Ý nghĩa nổi bật" text={overview.significance} />
          )}
        </div>
      ) : (
        <div className="prose-block">
          {(overview.paragraphs || []).map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          {overview.event && (
            <p>
              <strong>Sự kiện liên quan:</strong> {overview.event}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function StoryPoint({
  number,
  title,
  text,
}: {
  number: string;
  title: string;
  text: string;
}) {
  return (
    <article className="story-point">
      <span>{number}</span>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function DeepStory({
  artifact,
  story,
}: {
  artifact: Artifact;
  story: ArtifactStory;
}) {
  const images = story.deep.images.length ? story.deep.images : artifact.images;
  const source = story.deep.source || artifact.source;
  const sourceVerified = story.deep.source
    ? story.deep.source_verified === true
    : artifact.source_verified === true;
  return (
    <div className="deep-story">
      <span className="story-level-label">Khám phá đầy đủ</span>
      <div className="prose-block prose-wide">
        <p>{story.deep.description || artifact.description}</p>
        {(story.deep.event || artifact.event) && (
          <p>
            <strong>Sự kiện liên quan:</strong> {story.deep.event || artifact.event}
          </p>
        )}
        {story.deep.people && story.deep.people.length > 0 && (
          <p>
            <strong>Nhân vật liên quan:</strong> {story.deep.people.join(", ")}
          </p>
        )}
        {story.deep.related_events && story.deep.related_events.length > 0 && (
          <p>
            <strong>Nội dung liên quan:</strong>{" "}
            {story.deep.related_events.join(", ")}
          </p>
        )}
      </div>

      {images.length > 0 && (
        <div className="related-gallery">
          <h3>Hình ảnh và góc nhìn liên quan</h3>
          <div className="gallery-grid">
            {images.map((image) => (
              <StoryImage key={image.id} image={image} name={artifact.name} />
            ))}
          </div>
        </div>
      )}

      <aside className={`source-note ${sourceVerified ? "verified" : "pending"}`}>
        <strong>{sourceVerified ? "Nguồn tư liệu" : "Lưu ý về nguồn"}</strong>
        <p>
          {source ||
            "Nguồn tư liệu đang được bổ sung. Nội dung sâu này chưa nên được xem là đã kiểm chứng đầy đủ."}
        </p>
        {source && !sourceVerified && <p>Nguồn đã được ghi lại nhưng chưa được kiểm chứng đầy đủ.</p>}
      </aside>
    </div>
  );
}

function StoryImage({
  image,
  name,
  featured = false,
}: {
  image?: ArtifactImage | null;
  name: string;
  featured?: boolean;
}) {
  const url = toAssetUrl(image?.image_url || image?.url);
  if (!url) {
    return (
      <figure className={`story-image image-placeholder ${featured ? "featured" : ""}`}>
        <span aria-hidden="true">DiSản Lens</span>
        <figcaption>{image?.caption || `Hình ảnh ${name}`}</figcaption>
      </figure>
    );
  }
  return (
    <figure className={`story-image ${featured ? "featured" : ""}`}>
      {/* Backend image origins are configured at runtime. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt={image?.alt_text || image?.caption || `Hình ảnh ${name}`} />
      {image?.caption && <figcaption>{image.caption}</figcaption>}
    </figure>
  );
}
