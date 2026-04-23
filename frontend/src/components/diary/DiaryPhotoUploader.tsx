type DiaryPhotoUploaderProps = {
  photos: string[];
  onChange: (photos: string[]) => void;
};

export function DiaryPhotoUploader({ photos, onChange }: DiaryPhotoUploaderProps) {
  async function handleFiles(files: FileList | null) {
    if (!files) return;
    const loadedPhotos = await Promise.all(Array.from(files).map(readFileAsDataUrl));
    onChange([...photos, ...loadedPhotos]);
  }

  function readFileAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === "string") {
          resolve(reader.result);
        }
      };
      reader.readAsDataURL(file);
    });
  }

  return (
    <div className="photo-uploader">
      <label>
        <input type="file" accept="image/*" multiple onChange={(event) => handleFiles(event.target.files)} />
        <span>사진 업로드</span>
      </label>
      <div className="photo-preview-grid">
        {photos.map((photo, index) => (
          <button type="button" key={photo.slice(0, 40) + index} onClick={() => onChange(photos.filter((_, itemIndex) => itemIndex !== index))}>
            <img src={photo} alt={`여행 사진 ${index + 1}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
