package com.stemspro.app.player

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Decodes audio to ShortArray PCM (16-bit mono) using a growing flat array — NO boxing. */
class AudioDecoder {

    data class DecodeResult(
        val samples: ShortArray,
        val sampleRate: Int,
    )

    fun decode(filePath: String): DecodeResult? {
        var extractor: MediaExtractor? = null
        var codec: MediaCodec? = null
        var samples = ShortArray(44100 * 60)  // start with ~60s at 44.1kHz
        var count = 0

        return try {
            extractor = MediaExtractor()
            extractor.setDataSource(filePath)

            var trackIdx = -1
            var format: MediaFormat? = null
            for (i in 0 until extractor.trackCount) {
                val fmt = extractor.getTrackFormat(i)
                val mime = fmt.getString(MediaFormat.KEY_MIME) ?: ""
                if (mime.startsWith("audio/")) { trackIdx = i; format = fmt; break }
            }
            if (trackIdx < 0 || format == null) {
                extractor.release()
                return null
            }
            extractor.selectTrack(trackIdx)

            val sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            val channelCount = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            val mime = format.getString(MediaFormat.KEY_MIME)!!

            codec = MediaCodec.createDecoderByType(mime)
            codec.configure(format, null, null, 0)
            codec.start()

            val bufferInfo = MediaCodec.BufferInfo()
            var inputDone = false
            var sawEos = false

            while (!sawEos) {
                // Feed input
                if (!inputDone) {
                    val inIdx = codec.dequeueInputBuffer(5000)
                    if (inIdx >= 0) {
                        val inBuf = codec.getInputBuffer(inIdx)
                        if (inBuf != null) {
                            val size = extractor.readSampleData(inBuf, 0)
                            if (size >= 0) {
                                codec.queueInputBuffer(inIdx, 0, size, extractor.sampleTime, 0)
                                extractor.advance()
                            } else {
                                codec.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                inputDone = true
                            }
                        }
                    }
                }

                // Get output
                val outIdx = codec.dequeueOutputBuffer(bufferInfo, 5000)
                when {
                    outIdx >= 0 -> {
                        if (bufferInfo.size > 0) {
                            val outBuf = codec.getOutputBuffer(outIdx)!!
                            val byteBuf = ByteBuffer.allocate(bufferInfo.size).order(ByteOrder.nativeOrder())
                            outBuf.position(bufferInfo.offset)
                            outBuf.limit(bufferInfo.offset + bufferInfo.size)
                            byteBuf.put(outBuf)
                            byteBuf.flip()

                            val shortCount = bufferInfo.size / 2
                            // Ensure capacity
                            if (count + shortCount > samples.size) {
                                val newSize = maxOf(samples.size + (samples.size / 2), count + shortCount)
                                samples = samples.copyOf(newSize)
                            }

                            // Stereo→mono: average pairs
                            if (channelCount >= 2) {
                                val monoCount = shortCount / 2
                                for (j in 0 until monoCount) {
                                    val sum = (byteBuf.getShort().toInt() + byteBuf.getShort().toInt()) / 2
                                    samples[count++] = sum.toShort()
                                }
                            } else {
                                for (j in 0 until shortCount) {
                                    samples[count++] = byteBuf.getShort()
                                }
                            }
                        }
                        codec.releaseOutputBuffer(outIdx, false)
                        if (bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) sawEos = true
                    }
                    outIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> { /* accept, continue */ }
                    outIdx == MediaCodec.INFO_TRY_AGAIN_LATER -> { /* wait and loop */ }
                    else -> { /* other codes, ignore */ }
                }
            }

            codec.stop()
            codec.release()
            extractor.release()

            if (count == 0) return null
            Log.d("AudioDecoder", "decoded $filePath: ${count} samples @ ${sampleRate}Hz")
            DecodeResult(samples.copyOf(count), sampleRate)
        } catch (e: Exception) {
            Log.e("AudioDecoder", "decode failed for $filePath", e)
            null
        } finally {
            try { codec?.stop() } catch (_: Exception) {}
            try { codec?.release() } catch (_: Exception) {}
            try { extractor?.release() } catch (_: Exception) {}
        }
    }
}
