"use client"

import { useEffect, useRef } from "react"
import * as THREE from "three"

export function ShaderAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer
    uniforms: {
      time: { value: number }
      resolution: { value: THREE.Vector2 }
    }
    animationId: number
  } | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const container = containerRef.current

    // Initialize camera
    const camera = new THREE.Camera()
    camera.position.z = 1

    // Initialize scene
    const scene = new THREE.Scene()

    // Create geometry (PlaneBufferGeometry was removed from three r144+ -> PlaneGeometry)
    const geometry = new THREE.PlaneGeometry(2, 2)

    // Define uniforms
    const uniforms = {
      time: { value: 1.0 },
      resolution: { value: new THREE.Vector2() },
    }

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

      float random (in float x) {
          return fract(sin(x)*1e4);
      }
      float random (vec2 st) {
          return fract(sin(dot(st.xy,
                               vec2(12.9898,78.233)))*
              43758.5453123);
      }

      void main(void) {
        vec2 uv = (gl_FragCoord.xy * 2.0 - resolution.xy) / min(resolution.x, resolution.y);

        vec2 fMosaicScal = vec2(4.0, 2.0);
        vec2 vScreenSize = vec2(256,256);
        uv.x = floor(uv.x * vScreenSize.x / fMosaicScal.x) / (vScreenSize.x / fMosaicScal.x);
        uv.y = floor(uv.y * vScreenSize.y / fMosaicScal.y) / (vScreenSize.y / fMosaicScal.y);

        float t = time*0.06+random(uv.x)*0.4;
        float lineWidth = 0.0008;

        float intensity = 0.0;
        for(int j = 0; j < 3; j++){
          for(int i=0; i < 5; i++){
            intensity += lineWidth*float(i*i) / abs(fract(t - 0.01*float(j)+float(i)*0.01)*1.0 - length(uv));
          }
        }

        // RigFlow brand lime (#ccff00)
        vec3 lime = vec3(0.8, 1.0, 0.0);
        gl_FragColor = vec4(lime * intensity, 1.0);
      }
    `

    // Create material
    const material = new THREE.ShaderMaterial({
      uniforms: uniforms,
      vertexShader: vertexShader,
      fragmentShader: fragmentShader,
    })

    // Create mesh and add to scene
    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    // Initialize renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    container.appendChild(renderer.domElement)

    // Store references
    sceneRef.current = {
      renderer,
      uniforms,
      animationId: 0,
    }

    // Handle resize — size to the container box, not the window
    const onWindowResize = () => {
      const rect = container.getBoundingClientRect()
      renderer.setSize(rect.width, rect.height)
      uniforms.resolution.value.x = renderer.domElement.width
      uniforms.resolution.value.y = renderer.domElement.height
    }

    onWindowResize()
    window.addEventListener("resize", onWindowResize, false)

    // Animation loop
    const animate = () => {
      uniforms.time.value += 0.05
      renderer.render(scene, camera)

      const animationId = requestAnimationFrame(animate)
      if (sceneRef.current) {
        sceneRef.current.animationId = animationId
      }
    }

    // Only run while on-screen and the tab is visible, to spare the GPU.
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

    // Cleanup
    return () => {
      window.removeEventListener("resize", onWindowResize)
      observer.disconnect()
      document.removeEventListener("visibilitychange", syncPlayback)

      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.animationId)
        if (renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement)
        }
      }

      renderer.dispose()
      geometry.dispose()
      material.dispose()
    }
  }, [])

  return <div ref={containerRef} className="w-full h-full absolute" />
}
