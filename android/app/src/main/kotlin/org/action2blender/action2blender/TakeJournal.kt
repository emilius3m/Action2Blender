package org.action2blender.action2blender

import android.util.AtomicFile
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.Future

/** Append-only recording journal. The final JSON file is replaced atomically. */
class TakeJournal(private val directory: File) {
    private val writer = Executors.newSingleThreadExecutor()
    private var output: FileOutputStream? = null
    private var activeId: String? = null
    private var lastSync = 0L

    private fun waitFor(task: Future<*>) { task.get() }

    fun start(id: String, snapshot: JSONObject) {
        require(id.matches(Regex("[a-fA-F0-9-]{36}")))
        waitFor(writer.submit {
            output?.close()
            output = FileOutputStream(File(directory, "recording_$id.jsonl"), false)
            activeId = id
            writeLine(JSONObject().put("kind", "header").put("id", id).put("snapshot", snapshot), true)
        })
    }

    private fun writeLine(value: JSONObject, forceSync: Boolean) {
        val stream = output ?: return
        stream.write((value.toString() + "\n").toByteArray(Charsets.UTF_8))
        val now = System.nanoTime()
        if (forceSync || now - lastSync >= 1_000_000_000L) {
            stream.fd.sync()
            lastSync = now
        }
    }

    fun append(kind: String, value: JSONObject, forceSync: Boolean = false) {
        writer.execute {
            writeLine(JSONObject().put("kind", kind).put("value", value), forceSync)
        }
    }

    fun finish(id: String) {
        waitFor(writer.submit {
            if (activeId == id) {
                writeLine(JSONObject().put("kind", "complete"), true)
                output?.close()
                output = null
                activeId = null
            }
        })
    }

    fun savePending(take: JSONObject): File {
        val id = take.getString("id")
        val file = File(directory, "pending_$id.json")
        val atomic = AtomicFile(file)
        val stream = atomic.startWrite()
        try {
            stream.write(take.toString().toByteArray(Charsets.UTF_8))
            atomic.finishWrite(stream)
        } catch (error: Exception) {
            atomic.failWrite(stream)
            throw error
        }
        File(directory, "recording_$id.jsonl").delete()
        return file
    }

    /** Recover complete lines only; a crash may leave one truncated final line. */
    fun recover(): List<JSONObject> = directory.listFiles { file ->
        file.name.startsWith("recording_") && file.name.endsWith(".jsonl")
    }?.mapNotNull { file ->
        try {
            var header: JSONObject? = null
            val events = JSONArray()
            val markers = JSONArray()
            var complete = false
            val lines = file.readLines()
            for ((index, line) in lines.withIndex()) {
                    val entry = try { JSONObject(line) } catch (exc: Exception) {
                        if (index == lines.lastIndex) break
                        throw exc
                    }
                    when (entry.optString("kind")) {
                        "header" -> header = entry
                        "sample" -> events.put(entry.getJSONObject("value"))
                        "frame" -> markers.put(entry.getJSONObject("value"))
                        "complete" -> complete = true
                    }
            }
            val first = header ?: return@mapNotNull null
            if (events.length() == 0) return@mapNotNull null
            JSONObject().put("type", "take").put("id", first.getString("id"))
                .put("snapshot", first.getJSONObject("snapshot"))
                .put("events", events).put("frame_markers", markers)
                .put("partial", !complete)
        } catch (_: Exception) { null }
    } ?: emptyList()

    fun close() {
        waitFor(writer.submit { output?.fd?.sync(); output?.close(); output = null })
        writer.shutdown()
    }
}
