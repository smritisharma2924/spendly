const videoModal = document.querySelector("#video-modal");
const videoModalTrigger = document.querySelector("#video-modal-trigger");

if (videoModal && videoModalTrigger) {
    const videoModalClose = videoModal.querySelector(".video-modal-close");
    const videoModalPlayer = videoModal.querySelector("#video-modal-player");

    const openVideoModal = () => {
        videoModal.hidden = false;
        videoModalPlayer.src = videoModalPlayer.dataset.videoSrc;
        document.body.classList.add("video-modal-open");
        videoModalClose.focus();
    };

    const closeVideoModal = () => {
        videoModalPlayer.removeAttribute("src");
        videoModal.hidden = true;
        document.body.classList.remove("video-modal-open");
        videoModalTrigger.focus();
    };

    videoModalTrigger.addEventListener("click", openVideoModal);
    videoModalClose.addEventListener("click", closeVideoModal);

    videoModal.addEventListener("click", (event) => {
        if (event.target === videoModal) {
            closeVideoModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !videoModal.hidden) {
            closeVideoModal();
        }
    });
}
