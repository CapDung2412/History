"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { HeritageMindmap } from "@/components/heritage-mindmap";
import {
  ImageLightbox,
  type LightboxImage,
} from "@/components/image-lightbox";
import { CheckIcon } from "@/components/icons";
import { TtsControls } from "@/components/tts-controls";
import {
  ApiError,
  requestLearningContent,
  toAssetUrl,
  toThumbnailUrl,
  type LearningContentResponse,
  type LearningEvidenceReference,
} from "@/lib/api";
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
  const [lightboxImage, setLightboxImage] = useState<LightboxImage | null>(null);
  const [learning, setLearning] = useState<LearningContentResponse | null>(null);
  const [learningState, setLearningState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [learningError, setLearningError] = useState("");
  const learningRequestedRef = useRef(false);
  const learningAbortRef = useRef<AbortController | null>(null);
  const openImage = useCallback((image: LightboxImage) => setLightboxImage(image), []);
  const closeImage = useCallback(() => setLightboxImage(null), []);

  useEffect(() => {
    return () => learningAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (level === "quick" || learningRequestedRef.current) return;
    learningRequestedRef.current = true;
    const controller = new AbortController();
    learningAbortRef.current = controller;
    setLearningState("loading");
    setLearningError("");
    void requestLearningContent(artifact.item_id, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setLearning(response);
        setLearningState("ready");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        learningRequestedRef.current = false;
        setLearningState("error");
        setLearningError(
          error instanceof ApiError
            ? error.message
            : "Chưa tải được nội dung mở rộng từ máy chủ.",
        );
      });
  }, [artifact.item_id, level]);

  const narration = useMemo(() => {
    const generated = learning?.generation_status === "generated" ? learning.content : null;
    const generatedOneMinute = generated?.storytelling.one_minute.text.trim();
    if (level === "overview" && generatedOneMinute) return generatedOneMinute;
    if (level === "deep" && generated) {
      return uniqueText([
        generatedOneMinute || "",
        ...generated.deep_sections.flatMap((section) => [section.summary, section.body]),
      ]).join(". ");
    }
    return Array.from(new Set([
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
    ].filter(Boolean))).join(". ");
  }, [learning, level, story]);

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
        {level === "quick" && (
          <QuickStory artifact={artifact} story={story} onOpenImage={openImage} />
        )}
        {level === "overview" && (
          <OverviewStory
            artifact={artifact}
            story={story}
            onOpenImage={openImage}
            learning={learning}
            learningState={learningState}
            learningError={learningError}
          />
        )}
        {level === "deep" && (
          <DeepStory
            artifact={artifact}
            story={story}
            onOpenImage={openImage}
            learning={learning}
            learningState={learningState}
            learningError={learningError}
          />
        )}
      </div>

      <TtsControls text={narration} contentId={artifact.item_id} />
      <ImageLightbox image={lightboxImage} onClose={closeImage} />
    </section>
  );
}

function QuickStory({
  artifact,
  story,
  onOpenImage,
}: {
  artifact: Artifact;
  story: ArtifactStory;
  onOpenImage: (image: LightboxImage) => void;
}) {
  const image = story.quick.image || artifact.images[0];
  const recognitionDetail = specificRecognitionDetail(image, artifact.name);
  return (
    <div className="quick-story">
      <StoryImage image={image} name={artifact.name} featured onOpen={onOpenImage} />
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
          {recognitionDetail && (
            <div>
              <dt>Dấu hiệu nhận diện</dt>
              <dd>{recognitionDetail}</dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}

function OverviewStory({
  artifact,
  story,
  onOpenImage,
  learning,
  learningState,
  learningError,
}: StoryExplorerProps & {
  onOpenImage: (image: LightboxImage) => void;
  learning: LearningContentResponse | null;
  learningState: "idle" | "loading" | "ready" | "error";
  learningError: string;
}) {
  const overview = story.overview;
  const generatedOneMinute =
    learning?.generation_status === "generated"
      ? learning.content.storytelling?.one_minute?.text || ""
      : "";
  const overviewLead = generatedOneMinute || overview.description;
  const hasStructured =
    overview.what_it_is || overview.role || overview.context || overview.significance;
  const images = selectOverviewImages(artifact, story);
  return (
    <div className="overview-story">
      <div className="story-level-heading">
        <span className="story-level-label">Câu chuyện khoảng 1 phút</span>
        {generatedOneMinute && (
          <span className="story-generation-badge">
            AI biên soạn từ dữ liệu tham chiếu · {readingEstimate(generatedOneMinute)}
          </span>
        )}
      </div>
      {learningState === "loading" && (
        <aside className="learning-notice is-loading overview-source-notice" role="status">
          <strong>Đang tạo câu chuyện một phút</strong>
          <p>AI đang đối chiếu dữ liệu hiện vật và nguồn tham chiếu trước khi biên soạn.</p>
        </aside>
      )}
      {learningState === "error" && (
        <aside className="learning-notice is-fallback overview-source-notice" role="status">
          <strong>Chưa tạo được câu chuyện bằng AI</strong>
          <p>{learningError} Nội dung gốc từ dữ liệu hiện vật vẫn được hiển thị bên dưới.</p>
        </aside>
      )}
      {learningState === "ready" && learning && !generatedOneMinute && (
        <aside className="learning-notice is-fallback overview-source-notice">
          <strong>Đang dùng mô tả nguyên bản từ dữ liệu hiện vật</strong>
          <p>{learning.notice}</p>
        </aside>
      )}
      <div className="overview-layout">
        <div>
          {overviewLead && <p className="story-intro">{overviewLead}</p>}
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
          ) : !generatedOneMinute ? (
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
          ) : null}
        </div>
        {images.length > 0 && (
          <div className="overview-gallery" aria-label="Ảnh liên quan đến câu chuyện một phút">
            {images.map((image) => (
              <StoryImage
                key={image.id}
                image={image}
                name={artifact.name}
                onOpen={onOpenImage}
              />
            ))}
          </div>
        )}
      </div>
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
  onOpenImage,
  learning,
  learningState,
  learningError,
}: {
  artifact: Artifact;
  story: ArtifactStory;
  onOpenImage: (image: LightboxImage) => void;
  learning: LearningContentResponse | null;
  learningState: "idle" | "loading" | "ready" | "error";
  learningError: string;
}) {
  const images = story.deep.images.length ? story.deep.images : artifact.images;
  const source = story.deep.source || artifact.source;
  const sourceVerified = story.deep.source
    ? story.deep.source_verified === true
    : artifact.source_verified === true;
  const timeline = buildTimeline(artifact, images);
  const event = story.deep.event || artifact.event;
  const context = story.overview.context;
  const relatedEvents = uniqueText(story.deep.related_events || []).filter(
    (value) => value !== event,
  );
  const overview = story.deep.description || artifact.description;
  const overviewAlreadyShown = sameText(
    overview,
    story.overview.description || story.overview.paragraphs?.[0] || "",
  );
  const generated = learning?.generation_status === "generated" ? learning.content : null;
  const learningTimeline = learning?.content.timeline || [];
  const learningKeywords = learning?.content.keywords || [];
  const linkedReferences = uniqueLinkedReferences(learning?.references || []);
  const generalIntroduction =
    generated?.storytelling.one_minute.text || overview || story.overview.description;
  const mindmapTimeline = learningTimeline.length > 0
    ? learningTimeline
    : timeline.map((entry) => ({ ...entry, period: null }));

  return (
    <div className="deep-story">
      <span className="story-level-label">Khám phá đầy đủ</span>
      {learningState === "loading" && (
        <aside className="learning-notice is-loading" role="status">
          <strong>Đang kiểm tra dữ liệu học tập</strong>
          <p>Hệ thống đang đối chiếu dữ liệu hiện vật và bộ nhớ đệm…</p>
        </aside>
      )}
      {learningState === "error" && (
        <aside className="learning-notice is-fallback" role="status">
          <strong>Vẫn có thể tiếp tục khám phá</strong>
          <p>{learningError} Nội dung gốc từ JSON vẫn được giữ nguyên bên dưới.</p>
        </aside>
      )}
      {learningState === "ready" && learning && (
        <aside
          className={`learning-notice ${generated ? "is-generated" : "is-fallback"}`}
          role="status"
        >
          <strong>
            {generated
              ? "Nội dung AI có tham chiếu dữ liệu"
              : learning.source_status === "missing"
                ? "Dữ liệu hiện vật đang thiếu nguồn kiểm chứng"
                : "Đang dùng nội dung an toàn từ JSON"}
          </strong>
          <p>{learning.notice}</p>
          {generated && (
            <small>
              {learning.cache_status === "hit"
                ? "Đã dùng bản nội dung được lưu đệm."
                : "Nội dung mới đã vượt qua kiểm tra schema và tham chiếu."}
            </small>
          )}
        </aside>
      )}
      <div className="deep-section-list">
        {generalIntroduction && (
          <section className="deep-overview" aria-labelledby="deep-overview-title">
            <p className="eyebrow">Giới thiệu tổng quát</p>
            <h3 id="deep-overview-title">{artifact.name}</h3>
            <p>{generalIntroduction}</p>
            {generated && (
              <small>Phần dẫn nhập do AI biên soạn từ các dữ kiện có tham chiếu.</small>
            )}
          </section>
        )}

        <h3 className="deep-details-heading">Phân tích chi tiết</h3>
        {generated && generated.deep_sections.length > 0 ? (
          generated.deep_sections.map((section, index) => (
            <DeepSection key={`${section.key}-${section.title}`} title={section.title} defaultOpen={index === 0}>
              <div className="prose-block prose-wide">
                {section.summary !== section.body && <p className="story-intro">{section.summary}</p>}
                <p>{section.body}</p>
              </div>
              <SectionEvidence learning={learning} claimIds={section.claim_ids} />
            </DeepSection>
          ))
        ) : (
          <>
            {overview && !overviewAlreadyShown && (
              <DeepSection title="Tổng quan hiện vật" defaultOpen>
                <div className="prose-block prose-wide"><p>{overview}</p></div>
              </DeepSection>
            )}

            {(event || context || relatedEvents.length > 0) && (
              <DeepSection title="Bối cảnh và sự kiện">
                <div className="prose-block prose-wide">
                  {context && <p>{context}</p>}
                  {event && <p><strong>Sự kiện được ghi trong dữ liệu:</strong> {event}</p>}
                  {relatedEvents.length > 0 && (
                    <p><strong>Nội dung liên quan:</strong> {relatedEvents.join(", ")}</p>
                  )}
                </div>
              </DeepSection>
            )}
          </>
        )}

        {(learningTimeline.length > 0 || timeline.length > 0) && (
          <DeepSection title="Dòng thời gian">
            <ol className="artifact-timeline">
              {learningTimeline.length > 0
                ? learningTimeline.map((entry) => (
                    <li key={`${entry.year || entry.period}-${entry.label}`}>
                      <time dateTime={entry.year ? String(entry.year) : undefined}>
                        {entry.year ?? entry.period}
                      </time>
                      <span>{entry.label}</span>
                    </li>
                  ))
                : timeline.map((entry) => (
                    <li key={`${entry.year}-${entry.label}`}>
                      <time dateTime={String(entry.year)}>{entry.year}</time>
                      <span>{entry.label}</span>
                    </li>
                  ))}
            </ol>
          </DeepSection>
        )}

        {story.deep.people && story.deep.people.length > 0 && (
          <DeepSection title="Nhân vật liên quan">
            <ul className="fact-chip-list">
              {uniqueText(story.deep.people).map((person) => <li key={person}>{person}</li>)}
            </ul>
          </DeepSection>
        )}

        <DeepSection title="Mindmap ghi nhớ">
          <HeritageMindmap
            artifact={artifact}
            story={story}
            learningMindmap={learning?.content.mindmap}
            timeline={mindmapTimeline}
          />
        </DeepSection>

        {images.length > 0 && (
          <DeepSection title="Hình ảnh liên quan">
            <div className="gallery-grid">
              {images.map((image) => (
                <StoryImage
                  key={image.id}
                  image={image}
                  name={artifact.name}
                  onOpen={onOpenImage}
                />
              ))}
            </div>
          </DeepSection>
        )}

        {(learningKeywords.length > 0 || artifact.tags.length > 0) && (
          <DeepSection title="Từ khóa cần nhớ">
            <ul className="fact-chip-list">
              {(learningKeywords.length > 0
                ? learningKeywords.map((keyword) => keyword.term)
                : uniqueText(artifact.tags)
              ).map((tag) => <li key={tag}>{tag}</li>)}
            </ul>
          </DeepSection>
        )}

        <DeepSection title="Nguồn tham khảo">
          <aside className={`source-note ${sourceVerified ? "verified" : "pending"}`}>
            <strong>{sourceVerified ? "Nguồn tư liệu đã xác minh" : "Lưu ý về nguồn"}</strong>
            <p>
              {source || (linkedReferences.length > 0
                ? "Dữ liệu JSON chưa ghi nguồn; dưới đây là các nguồn web AI đã tìm để tham khảo."
                : "Chưa có nguồn kiểm chứng trong bộ dữ liệu.")}
            </p>
            {source && !sourceVerified && (
              <p>Nguồn đã được ghi lại nhưng chưa được kiểm chứng đầy đủ.</p>
            )}
            {linkedReferences.length > 0 && (
              <>
                <p><strong>Nguồn web có liên kết</strong></p>
                <ul className="web-source-list">
                  {linkedReferences.map((reference) => (
                    <li key={reference.url}>
                      <a href={reference.url} target="_blank" rel="noopener noreferrer">
                        {reference.label || "Mở nguồn tham khảo"}
                      </a>
                      {reference.value && <small>{shortEvidence(reference.value)}</small>}
                    </li>
                  ))}
                </ul>
                <p>Các nguồn do AI tìm trên web cần được đối chiếu trước khi dùng làm tài liệu chính thức.</p>
              </>
            )}
          </aside>
        </DeepSection>
      </div>
    </div>
  );
}

function StoryImage({
  image,
  name,
  featured = false,
  onOpen,
}: {
  image?: ArtifactImage | null;
  name: string;
  featured?: boolean;
  onOpen: (image: LightboxImage) => void;
}) {
  const url = toAssetUrl(image?.image_url || image?.url);
  const [failed, setFailed] = useState(false);
  const caption = image?.caption || name;
  const alt = image?.alt_text || image?.caption || `Hình ảnh ${name}`;
  if (!url) {
    return (
      <figure className={`story-image image-placeholder ${featured ? "featured" : ""}`}>
        <span aria-hidden="true">DiSản Lens</span>
        <figcaption>{caption}</figcaption>
      </figure>
    );
  }
  if (failed) {
    return (
      <figure className={`story-image image-placeholder ${featured ? "featured" : ""}`}>
        <span role="status">Chưa tải được ảnh</span>
        <figcaption>{caption}</figcaption>
      </figure>
    );
  }
  const displayWidth = featured ? 960 : 640;
  return (
    <figure className={`story-image ${featured ? "featured" : ""}`}>
      <button
        type="button"
        className="story-image-button"
        onClick={() => onOpen({ url, alt, caption: image?.caption || name })}
        aria-label={`Xem ảnh lớn: ${caption}`}
      >
        {/* Runtime backend URLs and width variants are not known at build time. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={toThumbnailUrl(url, displayWidth)}
          srcSet={([320, 640, 960] as const)
            .map((width) => `${toThumbnailUrl(url, width)} ${width}w`)
            .join(", ")}
          sizes={featured ? "(max-width: 800px) 100vw, 45vw" : "(max-width: 640px) 100vw, 33vw"}
          width={1200}
          height={900}
          loading={featured ? "eager" : "lazy"}
          fetchPriority={featured ? "high" : "auto"}
          decoding="async"
          alt={alt}
          onError={() => setFailed(true)}
        />
        <span className="story-image-zoom" aria-hidden="true">Xem lớn</span>
      </button>
      {image?.caption && <figcaption>{image.caption}</figcaption>}
    </figure>
  );
}

function DeepSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="deep-section" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        <span className="deep-section-marker" aria-hidden="true" />
      </summary>
      <div className="deep-section-content">{children}</div>
    </details>
  );
}

function SectionEvidence({
  learning,
  claimIds,
}: {
  learning: LearningContentResponse | null;
  claimIds: string[];
}) {
  if (!learning || claimIds.length === 0) return null;
  const claimSet = new Set(claimIds);
  const evidenceRefs = new Set(
    (learning.content.factual_claims || [])
      .filter((claim) => claimSet.has(claim.id))
      .flatMap((claim) => claim.evidence_refs),
  );
  const references = (learning.references || []).filter((reference) =>
    evidenceRefs.has(reference.ref),
  );
  if (references.length === 0) return null;
  return (
    <aside className="section-evidence" aria-label="Căn cứ dữ liệu cho phần này">
      <strong>Căn cứ dữ liệu</strong>
      <ul>
        {references.map((reference) => (
          <li key={reference.ref}>
            <span>{reference.label}:</span> {shortEvidence(reference.value)}
            {reference.url && (
              <a href={reference.url} target="_blank" rel="noreferrer">
                Mở nguồn
              </a>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function selectOverviewImages(artifact: Artifact, story: ArtifactStory): ArtifactImage[] {
  const available = story.deep.images.length ? story.deep.images : artifact.images;
  const ordered = available.length > 1 ? [...available.slice(1), available[0]] : available;
  const seen = new Set<string>();
  return ordered.filter((image) => {
    const key = image.id || image.image_url || image.url || image.filename;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 3);
}

function buildTimeline(
  artifact: Artifact,
  images: ArtifactImage[],
): Array<{ year: number; label: string }> {
  const entries: Array<{ year: number; label: string }> = [];
  if (artifact.year != null) {
    entries.push({ year: artifact.year, label: "Năm được ghi trong dữ liệu hiện vật" });
  }
  for (const image of images) {
    if (image.year == null) continue;
    entries.push({
      year: image.year,
      label: image.caption ? `Năm được ghi cho ảnh “${image.caption}”` : "Năm được ghi cho ảnh hiện vật",
    });
  }
  const seen = new Set<string>();
  return entries
    .filter((entry) => {
      const key = `${entry.year}:${entry.label}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((left, right) => left.year - right.year);
}

function uniqueText(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function sameText(left: string, right: string): boolean {
  if (!left || !right) return false;
  const normalize = (value: string) =>
    value.normalize("NFC").replace(/\s+/g, " ").trim().toLocaleLowerCase("vi-VN");
  return normalize(left) === normalize(right);
}

function shortEvidence(value: string, limit = 240): string {
  const normalized = value.normalize("NFC").replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const clipped = normalized.slice(0, limit - 1);
  const boundary = clipped.lastIndexOf(" ");
  return `${clipped.slice(0, Math.max(boundary, Math.floor(limit * 0.7)))}…`;
}

function readingEstimate(value: string): string {
  const wordCount = value.normalize("NFC").trim().split(/\s+/u).filter(Boolean).length;
  if (wordCount === 0) return "chưa có nội dung";
  const seconds = Math.max(1, Math.round((wordCount / 145) * 60));
  if (seconds < 50) return `${seconds} giây đọc`;
  if (seconds <= 75) return `khoảng 1 phút đọc · ${wordCount} từ`;
  return `khoảng ${Math.max(1, Math.round(seconds / 60))} phút đọc · ${wordCount} từ`;
}

function uniqueLinkedReferences(
  references: LearningEvidenceReference[],
): Array<LearningEvidenceReference & { url: string }> {
  const seen = new Set<string>();
  const linked: Array<LearningEvidenceReference & { url: string }> = [];
  for (const reference of references) {
    if (!reference.url) continue;
    let parsed: URL;
    try {
      parsed = new URL(reference.url);
    } catch {
      continue;
    }
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") continue;
    parsed.hash = "";
    const url = parsed.toString();
    const key = url.endsWith("/") ? url.slice(0, -1) : url;
    if (seen.has(key)) continue;
    seen.add(key);
    linked.push({ ...reference, url });
  }
  return linked;
}

function specificRecognitionDetail(
  image: ArtifactImage | null | undefined,
  artifactName: string,
): string | null {
  const view = image?.view?.normalize("NFC").trim();
  if (view && !/^goc-nhin-\d+$/i.test(view)) return view;
  const caption = image?.caption?.normalize("NFC").trim();
  if (!caption) return null;
  const normalizedCaption = caption.toLocaleLowerCase("vi-VN");
  const normalizedName = artifactName.normalize("NFC").trim().toLocaleLowerCase("vi-VN");
  if (
    normalizedCaption.startsWith("ảnh ") ||
    normalizedCaption.includes(normalizedName)
  ) {
    return null;
  }
  return caption;
}
