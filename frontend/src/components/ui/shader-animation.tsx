"use client"

import { useEffect, useRef } from "react"
import * as THREE from "three"

export function ShaderAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<{
    camera: THREE.Camera
    scene: THREE.Scene
    renderer: THREE.WebGLRenderer
    uniforms: {
      time: { type: string; value: number }
      resolution: { type: string; value: THREE.Vector2 }
    }
    animationId: number
  } | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const container = containerRef.current

    // Vertex shader
    const vertexShader = `
      void main() {
        gl_Position = vec4( position, 1.0 );
      }
    `

    // Fragment shader
    const fragmentShader = `
      #define TWO_PI 6.2831853072
      #define PI 3.14159265359

      precision highp float;
      uniform vec2 resolution;
      uniform float time;

      void main(void) {
        vec2 uv = (gl_FragCoord.xy * 2.0 - resolution.xy) / min(resolution.x, resolution.y);
        float t = time*0.05;
        float lineWidth = 0.002;

        float intensity = 0.0;
        for(int j = 0; j < 3; j++){
          for(int i=0; i < 5; i++){
            intensity += lineWidth*float(i*i) / abs(fract(t - 0.01*float(j)+float(i)*0.01)*5.0 - length(uv) + mod(uv.x+uv.y, 0.2));
          }
        }

        // RigFlow brand lime (#ccff00)
        vec3 lime = vec3(0.8, 1.0, 0.0);
        gl_FragColor = vec4(lime * intensity, 1.0);
      }
    `

    // Initialize Three.js scene
    const camera = new THREE.Camera()
    camera.position.z = 1

    const scene = new THREE.Scene()
    const geometry = new THREE.PlaneGeometry(2, 2)

    const uniforms = {
      time: { type: "f", value: 1.0 },
      resolution: { type: "v2", value: new THREE.Vector2() },
    }

    const material = new THREE.ShaderMaterial({
      uniforms: uniforms,
      vertexShader: vertexShader,
      fragmentShader: fragmentShader,
    })

    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)

    container.appendChild(renderer.domElement)

    // Handle window resize
    const onWindowResize = () => {
      const width = container.clientWidth
      const height = container.clientHeight
      renderer.setSize(width, height)
      uniforms.resolution.value.x = renderer.domElement.width
      uniforms.resolution.value.y = renderer.domElement.height
    }

    // Initial resize
    onWindowResize()
    window.addEventListener("resize", onWindowResize, false)

    // Store scene references for cleanup
    sceneRef.current = {
      camera,
      scene,
      renderer,
      uniforms,
      animationId: 0,
    }

    // Animation loop
    const animate = () => {
      uniforms.time.value += 0.05
      renderer.render(scene, camera)

      const animationId = requestAnimationFrame(animate)
      if (sceneRef.current) {
        sceneRef.current.animationId = animationId
      }
    }

    // Only run the loop while the canvas is on-screen and the tab is visible,
    // so it doesn't burn GPU as an off-screen background.
    let running = false
    let onScreen = false

    const start = () => {
      if (running) return
      running = true
      if (sceneRef.current) {
        sceneRef.current.animationId = requestAnimationFrame(animate)
      }
    }

    const stop = () => {
      if (!running) return
      running = false
      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.animationId)
      }
    }

    const syncPlayback = () => {
      if (onScreen && !document.hidden) start()
      else stop()
    }

    const observer = new IntersectionObserver(
      (entries) => {
        onScreen = entries[0]?.isIntersecting ?? false
        syncPlayback()
      },
      { threshold: 0 },
    )
    observer.observe(container)
    document.addEventListener("visibilitychange", syncPlayback)

    // Cleanup function
    return () => {
      window.removeEventListener("resize", onWindowResize)
      observer.disconnect()
      document.removeEventListener("visibilitychange", syncPlayback)

      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.animationId)

        if (container && sceneRef.current.renderer.domElement) {
          container.removeChild(sceneRef.current.renderer.domElement)
        }

        sceneRef.current.renderer.dispose()
        geometry.dispose()
        material.dispose()
      }
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="w-full h-screen"
      style={{
        background: "#000",
        overflow: "hidden",
      }}
    />
  )
}
